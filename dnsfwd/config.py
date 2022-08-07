import json
from collections import abc
from . import util

def load_config(o):
	"""
	:return: A dict of hierarchical domain name. The value of the dict is a tuple of
	         (rule, child)
	"""
	if not isinstance(o, abc.Iterable):
		raise ValueError("Argument is not an iterable.")
	ret = {}
	for rule in o:
		if not isinstance(rule, abc.Mapping):
			raise ValueError("A rule must be a dictionary.")
		_load_rule_entry(rule, ret)
	return ret

# validators for each rule
def _check_array(o):
	if isinstance(o, str):
		return False
	return isinstance(o, abc.Sequence)

def _check_ipv4_addr(addr):
	"""
	:param addr str: Must be in IPv4 quad dotted notation
	"""
	ERRMSG = "Invalid IPv4 address"
	s = addr.split(".")
	if len(s) != 4:
		raise ValueError(ERRMSG)
	for i in s:
		if not (0 <= int(i) < 256):
			raise ValueError(ERRMSG)

def _validate_rule(rule):
	# suffixes
	v = rule.get("suffixes", None)
	if v:
		if not _check_array(v):
			raise ValueError("'suffixes' must be a list.")
		if not v:
			raise ValueError("'suffixes' must have at least one entry.")

	# forwardto and overrideto is mutually exclusive
	if (("forwardto" in rule) and ("overrideto" in rule)) or \
		(("forwardto" not in rule) and ("overrideto" not in rule)):
		raise ValueError("either 'forwardto' or 'overrideto' must be specified, but not both.")

	# forwardto
	v = rule.get("forwardto", None)
	if v:
		if not _check_array(v):
			raise ValueError("'forwardto' must be a list.")
		if not v:
			raise ValueError("'forwardto' must have at least one entry.")
		for a in v:
			_check_ipv4_addr(a)

	# overrideto
	if "overrideto" in rule:
		_check_ipv4_addr(rule["overrideto"])

	# forcecache
	if not isinstance(rule.get("forcecache", 0), int):
		raise ValueError("'forcecache' must be an integer.")

	# extendcacheonreq
	if not isinstance(rule.get("extendcacheonreq", False), bool):
		raise ValueError("'extendcacheonreq' must be a bool.")

def _add_entry(components, rule, ret):
	for c in components:
		# [rule, child]
		entry = ret.setdefault(c, [None, {}])
		_, ret = entry
	if entry[0] is not None:
		raise ValueError(f"Duplicate rule for '{'.'.join(components)}'.")
	entry[0] = rule

def _load_rule_entry(rule, ret):
	_validate_rule(rule)
	# additional checking
	if "forcecache" in rule and rule["forcecache"] < 1:
		raise ValueError("'forcecache' value must be at least 1 second.")

	suffixes = rule.get("suffixes", None)
	if suffixes:
		for s in suffixes:
			_add_entry(util.parse_dns_name(s), rule, ret)
	else:
		_add_entry([""], rule, ret)
