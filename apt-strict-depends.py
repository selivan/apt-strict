#/usr/bin/env python2

import apt
import sys

from pprint import pprint

LOOP_LIMIT = 50

packages = {
    'yandex-dns-monkey': { 'version': '0.54', 'resolved': False, 'dependant': None}
}

cache = apt.cache.Cache()

loop_counter=0
while True:
    for pkg, props in packages.iteritems():
        if not props['resolved']: break
    else:
        break

    package = apt.package.Package()
    version = props['version']
    if version is None or len(version) == 0:
        version

    props['resolved'] = True

    loop_counter += 1;
    if loop_counter > 50:
        print >> sys.stderr, 'Failed to resolve dependencies in %d' % LOOP_LIMIT
        sys.exit(1)

pprint(packages)
sys.exit(0)
