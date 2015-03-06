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


def report_changes(cache):
    """Return string - all marked changes in cache"""
    delete = []; downgrade = []; install = []; keep = []; reinstall = []; upgrade = []
    for pkg in cache.get_changes():
        if   pkg.marked_delete:    delete.append((pkg.name, pkg.candidate.version))
        elif pkg.marked_downgrade: downgrade.append((pkg.name, pkg.candidate.version))
        elif pkg.marked_install:   install.append((pkg.name, pkg.candidate.version))
        elif pkg.marked_keep:      keep.append((pkg.name, pkg.candidate.version))
        elif pkg.marked_reinstall: reinstall.append((pkg.name, pkg.candidate.version))
        elif pkg.marked_upgrade:   upgrade.append((pkg.name, pkg.candidate.version))
    result = ''
    if len(delete) != 0:
        result += '\nDelete:%d: ' % len(delete)
        result += ' '.join(str(i[0])+'='+str(i[1]) for i in delete)
    elif len(downgrade) != 0:
        result += '\nDowngrade:%d: ' % len(downgrade)
        result += ' '.join(str(i[0])+'='+str(i[1]) for i in downgrade)
    elif len(install) != 0:
        result += '\nInstall:%d: ' % len(install)
        result += ' '.join(str(i[0])+'='+str(i[1]) for i in install)
    elif len(keep) != 0:
        result += '\nKeep:%d: ' % len(keep)
        result += ' '.join(str(i[0])+'='+str(i[1]) for i in keep)
    elif len(reinstall) != 0:
        result += '\nReinstall:%d: ' % len(reinstall)
        result += ' '.join(str(i[0])+'='+str(i[1]) for i in reinstall)
    elif len(upgrade) != 0:
        result += '\nUpgrade:%d: ' % len(upgrade)
        result += ' '.join(str(i[0])+'='+str(i[1]) for i in upgrade)
    return result


def mark_changes(package_list, cache):
    """Mark changes from list in cache"""
    # packlage_list = {'name': {'version': 'x', 'resolved': False}}
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
    if package_list[package_name]['resolved']:
        debug('resolve_deps incorrect call: package %s already resolved' % package_name)
        return

    # Virtual package handling
    if package_name not in package_list:
        providing = cache.get_providing_packages(package_name)
        if len(providing) == 0:
            die('resolve_deps incorrect call: %s is not in package_list and is not virtual package' % package_name)
        # try to mark apropriate package providing
        else:
            debug('%s is virtual package, trying to resolve...' % package_name)
            # get current machine architecture
            arch = cache['dpkg'].candidate.architecture
            for pkg in providing:
                if pkg in cache and ( cache[pkg].candidate.architecture == arch or arch == 'all' ):
                    if pkg not in package_list:
                        package_list[pkg] = {'version': None, 'resolved': False}
                    return
            else: # for
                die('resolve_deps failed: no package can provide virtual package %s' % package_name)

    package_props = package_list[package_name]

    # Get required package version
    pkg = cache[package_name]
    if package_props['version'] is None or package_props['version'] == '':
        ver = pkg.candidate
    elif package_props['version'] in pkg.versions.keys():
        ver = pkg.versions[package_props['version']]
    else:
        die('Version %s for package %s not found' % (package_props['version'], package_name))
        ver = None # never happens, just to supress PyCharm warning

    # Process dependencies
    for dep in ver.dependencies:

        dep_resolved = False

        # Check if any of variants already installed
        # If precise version required - handle it
        for bdep in dep.or_dependencies:

            # Save resolved state: prevent endless loop
            if bdep.name in package_list:
                bdep_resolved = package_list[bdep.name]['resolved']
            else:
                bdep_resolved = False

            # One of dependencies variant is installed
            if bdep.name in cache and cache[bdep.name].installed is not None:
                # Found installed dependency for which we need precise version
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

# Clean from already installed for 'install-only-new'
if ACTION == 'install-only-new':
    packages = { k:v for k,v in orig_packages if cache[k].installed is None }

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

debug('# packages resolved: %d' % len(packages))
# Clear list from already installed packages without  explicit versions
tmp = {k:v for (k,v) in packages.iteritems() if cache[k].installed is None or v['version'] is not None }
packages=tmp
debug('# packages after first cleanup: %d' % len(packages))
# Clear list from already installed packages with necessary version
# TODO
tmp = {k:v for (k,v) in packages.iteritems() if not ( cache[k].installed is not None and cache[k].installed.version == v['version'] ) }
packages=tmp
debug('# packages after second cleanup: %d' % len(packages))

debug('result: \n' + pformat(packages))

mark_changes(packages, cache)

# Already installed packages excluded from list for 'install-only-new', so actions are similar
if ACTION == 'install' or ACTION == 'install-only-new':

    print report_changes(cache)

    if cache.broken_count != 0:
        die('Broken packages: %d' % cache.broken_count)

    if cache.dpkg_journal_dirty:
        die('dpkg was interrupted. Try to fix: dpkg --configure -a')

    try:
        cache.fetch_archives()
    except Exception, e:
        die('Failed to fetch archives: %s' % e.__str__())

    try:
        cache.commit()
    except Exception, e:
        die('Failed to commit changes')

elif ACTION == 'resolve':
    print report_changes(cache)
else:
    parser.print_usage()
    die('Unknown action %s' % ACTION)

sys.exit(0)
