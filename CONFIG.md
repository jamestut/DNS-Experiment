# Configuration Files

The configuration file is a JSON array, each array item has the following attributes:

- `suffixes`  
  List of domain suffixes that the rule should be matched to. Only ASCII "LDH" domain names are supported. If this attribute does not exist, then this rule will be used as the default rule. *For each configuration file, there must be exactly one default rule*.
  Domain names can optionally include the trailing `.`.
- `forwardto`  
  List of upstream DNS IPv4 addresses that the request should be forwarded to. Lower-indexed items takes precedence. *Must be specified if `overrideto` is not specified, must not be specified otherwise.*
- `overrideto`  
  If specified, always return an A record of the specified IP address rather than forwarding the domain. By default, TTL is set to 300 seconds and by configured by setting the `forcecache` option. *Must be specified if `forwardto` is not specified, must not be specified otherwise.*
- `forcecache`  
  Specify how long the forwarder's response should be cached in seconds since the last forwarder's response. This influences `overrideto` response, but does not change `forwardto` TTL.
- `extendcacheonreq`  
  Only applies if `forcecache` is set. If set to `true`, this will renew the cached forwarder's response expiry time everytime that particular response is requested.

## Matching Rule

- The suffix or domain length is based on the number of components (e.g. `subdomain.example.com` will have 3 components), and **not** the number of characters.
- The rule that have the longest suffix that matches the input domain wins.
  - If there are multiple matching rules having the same length suffix, an undefined rule of those matching rules will be used.
- If there is no matching rule, the default rule will be used.

