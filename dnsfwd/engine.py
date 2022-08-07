import dnslib
import socket
import select
import pdb
from threading import Lock
from collections import namedtuple, abc
from datetime import datetime, timedelta
from . import util
from .log import log

# update_on_req should be no. of seconds to renew or None
CacheUpdateInfo = namedtuple("CacheUpdateInfo", ["update_on_req", "expire"])

# TTL for overriden requests if 'forcecache' is not specified
DEFAULT_OVERRIDE_TTL = 300

class Engine:
	def __init__(self, ds):
		self._ds = ds
		self._cache = {}
		self._cache_lock = Lock()

		self._malformed_req = dnslib.DNSRecord(
			header=dnslib.DNSHeader(qr=dnslib.QR.RESPONSE, ra=1,
				rcode=dnslib.RCODE.FORMERR))

	def compute_response(self, data):
		# if parse error, do not reply!
		try:
			req = dnslib.DNSRecord.parse(data)
		except:
			log(2, "Received malformed DNS request. Not replying.")
			return None
		# check request sanity
		if req.header.get_qr() != dnslib.QR.QUERY or \
			req.header.get_opcode() != dnslib.OPCODE.QUERY:
			log(2, "Received malformed DNS request with "
				f"QR={dnslib.QR.get(req.header.get_qr())} "
				f"OPCODE={dnslib.OPCODE.get(req.header.get_opcode())}")
			return _make_basic_response(req)

		# make sure there are exactly one A question
		# also zaps AAAA (IPv6) requests!
		question = None
		ip6qs = []
		for i, q in enumerate(req.questions):
			if q.qtype == dnslib.QTYPE.A:
				question = q
			elif q.qtype == dnslib.QTYPE.AAAA:
				ip6qs.append(i)
		for i in reversed(ip6qs):
			del req.questions[i]
		req.set_header_qa()

		if not question:
			log(2, "DNS request have no question.")
			return _make_basic_response(req)
		if len(req.questions) > 1:
			log(2, "DNS request have multiple questions, which is not supported.")
			return _make_basic_response(req)

		reqtime = datetime.utcnow()

		fqdn = q.qname.idna()
		log(3, f"{fqdn}: Got request.")
		# check cache
		with self._cache_lock:
			entry, upd_info = self._cache.get(fqdn, (None, None))
			if upd_info is not None:
				if reqtime > upd_info.expire:
					# expired entry. remove and do business as usual
					del self._cache[fqdn]
				else:
					# cache hit!
					log(3, f"{fqdn}: Serving from cache.")
					if upd_info.update_on_req:
						upd_info.expire = reqtime + timedelta(
							seconds=upd_info.update_on_req)
					entry.header.id = req.header.id
					return entry.pack()

		# no cache hit, check rule
		fqdnc = util.parse_dns_name(fqdn)
		if fqdnc is None:
			log(2, f"{fqdn}: Unsupported domain name.")
			return _make_basic_response(req)

		# traverse rule
		rule = None
		dsl = self._ds
		for component in fqdnc:
			if component not in dsl:
				break
			crule, dsl = dsl[component]
			# most specific rule takes precedence
			if crule is not None:
				rule = crule

		if rule is None:
			log(2, f"{fqdn}: No rule found.")
			return _make_basic_response(req, nslib.RCODE.NXDOMAIN)

		rs = self._process_rule(req, fqdn, rule)
		if not rs:
			return _make_basic_response(req, dnslib.RCODE.SERVFAIL)
		return rs

	def _process_rule(self, req, fqdn, rule):
		override = rule.get("overrideto", None)
		if override:
			rs = req.reply()
			ttl = rule.get("forcecache", DEFAULT_OVERRIDE_TTL)
			rs.add_answer(
				dnslib.RR(fqdn, dnslib.QTYPE.A, rdata=dnslib.A(override), ttl=ttl))
			log(3, f"{fqdn}: Result override to '{override}'")
			return rs.pack()

		# normal forwarding approach
		fwdest = rule['forwardto']
		log(3, f"{fqdn}: Forward request to: {fwdest}")
		try:
			rs, responder = _parallel_udp_send_and_wait(req.pack(), fwdest)
		except TimeoutError:
			log(2, f"{fqdn}: Timeout requesting from forwarder {fwdest}")
			return None
		try:
			rso = dnslib.DNSRecord.parse(rs)
		except DNSError as ex:
			log(2, f"{fqdn}: Unknown DNS response from forwarder: {ex}")
			return None
		log(3, f"{fqdn}: Got response from {responder}.")

		# validate response
		if rso.header.get_qr() != dnslib.QR.RESPONSE or \
			rso.header.get_opcode() != dnslib.OPCODE.QUERY:
			log(2, f"{fqdn}: Received malformed DNS response from forwarder with "
					f"QR={dnslib.QR.get(rso.header.get_qr())} "
					f"OPCODE={dnslib.OPCODE.get(rso.header.get_opcode())}")
			return None

		# zap IPv6
		tozap = [i for i, v in enumerate(rso.rr) if v.rtype == dnslib.QTYPE.AAAA]
		if tozap:
			for i in reversed(tozap):
				del rso.rr[i]
			rso.set_header_qa()

		# all processing done. serialize to bytearray for return.
		rs = rso.pack()

		# determine how long to cache
		cachedur = rule.get("forcecache", None)
		if cachedur is None and rso.rr:
			cachedur = min((r.ttl for r in rso.rr))

		if cachedur:
			update_on_req = rule.get("extendcacheonreq", False) \
				if "forcecache" in rule else False
			expire = datetime.utcnow() + timedelta(seconds=cachedur)
			with self._cache_lock:
				self._cache[fqdn] = (rso, CacheUpdateInfo(update_on_req, expire))

		return rs

def _make_basic_response(req, rcode=dnslib.RCODE.FORMERR):
	r = req.reply()
	r.header.set_rcode(rcode)
	return r.pack()

# TODO: make timeout configurable
def _parallel_udp_send_and_wait(data, hosts, port=53, timeout=5):
	"""
	Perform a parallel requests to the specified hosts and wait for reply.
	"""
	if isinstance(hosts, str):
		hosts = [hosts]
	elif not isinstance(hosts, abc.Sequence):
		raise ValueError("'hosts' must be a sequence object.")

	socks = [socket.socket(socket.AF_INET, socket.SOCK_DGRAM) for _ in range(len(hosts))]
	sockmap = {s.fileno(): i for i, s in enumerate(socks)}
	try:
		p = select.poll()
		for s, host in zip(socks, hosts):
			s.sendto(data, (host, port))
			p.register(s, select.POLLIN)

		rdy = p.poll(timeout * 1000)
		if not rdy:
			raise TimeoutError()
		# only take the first entry if more than one are ready
		rdyidx = sockmap[rdy[0][0]]
		s = socks[rdyidx]
		resp, _ = s.recvfrom(8192)
		return resp, hosts[rdyidx]
	finally:
		# Unix socket will generate a random UDP sport for each socket object.
		# Therefore the socket's lifetime is tied to the request
		for s in socks:
			s.close()
