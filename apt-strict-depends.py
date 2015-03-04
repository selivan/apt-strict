#/usr/bin/env python2

import apt
import sys

from pprint import pprint, pformat

def die(message, exit_code=1):
    print >> sys.stderr, message
    sys.exit(exit_code)

def debug(message):
    if DEBUG: print >> sys.stderr, message

def resolve_deps(package_name, package_list, cache):
    """Resolve package dependencies and add them to package_list
    package_name indicates entry in package_list"""
    # debug('resolve_deps(%s)' % package_name)

    # Check correct call
    if package_name not in package_list:
        die('ERROR: Internal error')
    if package_list[package_name]['resolved']:
         debug('resolve_deps incorrect call: package %s already resolved' % package_name)
         return True

    package_props = package_list[package_name]

    # Get required package version
    pkg = cache[package_name]
    if package_props['version'] is None or package_props['version'] == '':
        ver = pkg.candidate
    elif package_props['version'] in pkg.versions.keys():
        ver = pkg.versions[package_props['version']]
    else:
        die('ERROR: Version %s for package %s not found' % (package_props['version'], package_name))

    # Process dependencies
    for dep in ver.dependencies:

        dep_resolved = False

        # Check if any of variants already installed
        # If precise version required - handle it
        for bdep in dep.or_dependencies:

            # save resolved state: prevent endless loop
            if bdep.name in package_list:
                bdep_resolved = package_list[bdep.name]['resolved']
            else:
                bdep_resolved = False

            if bdep.name in cache and cache[bdep.name].installed is not None:
                # found installed dependency for which we need precise version
                if bdep.relation == '=':
                    package_list[bdep.name] = {'version': bdep.version, 'resolved': bdep_resolved}
                else:
                    package_list[bdep.name] = {'version': None, 'resolved': bdep_resolved}
                dep_resolved = True
                break

        # No already installed variants found - get first
        # If precise version required - handle it
        if not dep_resolved:
            bdep = dep.or_dependencies.pop()

            if bdep.name in package_list:
                bdep_resolved = package_list[bdep.name]['resolved']
            else:
                bdep_resolved = False

            if bdep.relation == '=':
                package_list[bdep.name] = {'version': bdep.version, 'resolved': bdep_resolved}
            else:
                package_list[bdep.name] = {'version': None, 'resolved': bdep_resolved}

    package_list[package_name]['resolved'] = True

# Parse command-line arguments
# ...

LOOP_LIMIT = 10000
DEBUG = True

packages = {
    'pgpool2': {'version': '3.3.2-1ubuntu1', 'resolved': False, 'flag': False}
}
orig_packages=packages.copy()

# Initilize
cache = apt.cache.Cache()


# First cycle - resolve packages with explicit versions
loop_counter = 0
loop_finished = False
while not loop_finished:
    loop_finished = True
    for name, props in packages.iteritems():
        if props['resolved'] is False and props['version'] is not None and props['version'] != '':
            loop_finished = False
            break # for
    if not loop_finished:
        resolve_deps(name, packages, cache)

    loop_counter += 1
    if loop_counter > LOOP_LIMIT:
        die('Failed(1) to resolve dependencies in %d loops' % LOOP_LIMIT)

# Second cycle - resolve packages without explicit versions
loop_counter = 0
loop_finished = False
while not loop_finished:
    loop_finished = True
    for name, props in packages.iteritems():
        if props['resolved'] is False and (props['version'] is None or props['version'] != ''):
            loop_finished = False
            break # for
    if not loop_finished:
        resolve_deps(name, packages, cache)

    loop_counter += 1
    if loop_counter > LOOP_LIMIT:
        die('Failed(1) to resolve dependencies in %d loops' % LOOP_LIMIT)

debug(len(packages))
# Clear list from already installed packages without  explicit versions
tmp = {k:v for (k,v) in packages.iteritems() if cache[k].installed is None or v['version'] is not None }
packages=tmp
debug(len(packages))
# Clear list from already installed packages with necessary version
# TODO

print 'result:'
pprint(packages)

for k,v in packages.iteritems():
    print k
    pprint(v)
    pprint(cache[k].versions)
    if v['version'] is not None:
        cache[k].candidate = cache[k].versions[v['version']]
    cache[k].mark_install()


print cache.install_count

sys.exit(0)
