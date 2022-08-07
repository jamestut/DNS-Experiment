import re

# besides the top level ".", there must be at least one char in the domain name
_dns_name_component_re = re.compile(r'[a-z0-9\-]+')
def parse_dns_name(o):
	if o in ("", "."):
		return [""]
	r = []
	if o[-1] != ".":
		r.append("")
	r.extend(reversed(o.lower().split('.')))
	for i in range(1, len(r)):
		if not _dns_name_component_re.fullmatch(r[i]):
			return None
	return r
