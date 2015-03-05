#/usr/bin/env python2

import apt
import sys
from optparse import OptionParser
from pprint import pprint, pformat


def die(message, exit_code=1):
    print >> sys.stderr, 'ERROR: ' + message
    sys.exit(exit_code)


def debug(message):
    if DEBUG: print >> sys.stderr, message


def mark_changes(package_list, cache):
    """Mark changes from list in cache"""
    # {'name': {'version': 'x', 'resolved': False}}
    for k,v in package_list.iteritems():
        if v['version'] is not None and v['version'] != '':
            if v['version'] not in cache[k].versions:
                die('Could not find %s version %s in cache' % (k, v['version']))
            cache[k].candidate = cache[k].versions[v['version']]
        cache[k].mark_install()


def resolve_deps(package_name, package_list, cache):
    """Resolve package dependencies and add them to package_list
    package_name indicates entry in package_list"""
    # debug('resolve_deps(%s)' % package_name)

    # Check correct call
    if package_name not in package_list:
        die('Internal error')
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
        die('Version %s for package %s not found' % (package_props['version'], package_name))

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
    # // resolve_deps

# Options

LOOP_LIMIT = 10000

# Parse command-line arguments
# ...
parser = OptionParser(usage='Usage: %prog [options] install|install-only-new|resolve pkg1 pkg2=version2 ...')
parser.add_option('-d', '--debug', action='store_true', dest='debug', default=False, help='Enable debugging')
#parser.add_option('-y', '--yes', dest='YES', help='Do all actions without confirmation')
#parser.add_option('-s', '--simulate', dest='SIMULATE', help='simulate what will happen, no real action')

options, args = parser.parse_args()
if len(args) < 2:
    parser.print_help()
    die('Too few arguments')

ACTION = args[0]
if ACTION not in ('install', 'install-only-new', 'resolve'):
    parser.print_help()
    die('Invalid argument %s')

DEBUG = options.debug

# {'name': {'version': 'x', 'resolved': False}}
packages = {}

for i in args[1:]:
    if '=' not in i:
        packages[i] = {'version': None, 'resolved': False}
    else:
        packages[i.split('=')[0]] = {'version': i.split('=')[1], 'resolved': False}

orig_packages=packages.copy()

# Initilize apt cache interface
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
        die('Failed(2) to resolve dependencies in %d loops' % LOOP_LIMIT)

debug(len(packages))
# Clear list from already installed packages without  explicit versions
tmp = {k:v for (k,v) in packages.iteritems() if cache[k].installed is None or v['version'] is not None }
packages=tmp
debug(len(packages))
# Clear list from already installed packages with necessary version
# TODO

debug('result: \n' + pformat(packages))

if ACTION == 'install':

    mark_changes(packages, cache)

    print 'Packages to install: %d' % cache.install_count
    print 'Packages to keep: %d' % cache.keep_count
    print 'Packages to delete: %d' % cache.delete_count

    if cache.broken_count != 0:
        die('Broken packages: %d' % cache.broken_count)

    if cache.dpkg_journal_dirty:
        die('ERROR: dpkg was interrupted. Try to fix: dpkg --configure -a')

    try:
        cache.fetch_archives()
    except Exception, e:
        die('ERROR: failed to fetch archives: %s' % e.__str__())

    try:
        cache.commit()
    except Exception, e:
        die('ERROR: Failed to commit')

elif ACTION == 'install-only-new':
    die('%s not implemented' % ACTION)
elif ACTION == 'resolve':
    die('%s not implemented' % ACTION)

sys.exit(0)
