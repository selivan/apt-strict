#!/usr/bin/env python2

import apt
import sys
from optparse import OptionParser
from pprint import pprint, pformat


def die(message, exit_code=1):
    print >> sys.stderr, 'ERROR: ' + message
    sys.exit(exit_code)


def debug(message):
    if DEBUG: print >> sys.stderr, message


def report_changes(cache, result=None):
    """Return string - all marked changes in cache.
    Optionaly write detailed changes to result dict:
    {'delete': ['pkg1', 'pkg2'], 'downgrade': ['pkg3', 'pkg4'], ...}
    """
    delete = []; downgrade = []; install = []; keep = []; reinstall = []; upgrade = []
    for pkg in cache.get_changes():
        if   pkg.marked_delete:    delete.append((pkg.name, pkg.candidate.version))
        elif pkg.marked_downgrade: downgrade.append((pkg.name, pkg.candidate.version))
        elif pkg.marked_install:   install.append((pkg.name, pkg.candidate.version))
        elif pkg.marked_keep:      keep.append((pkg.name, pkg.candidate.version))
        elif pkg.marked_reinstall: reinstall.append((pkg.name, pkg.candidate.version))
        elif pkg.marked_upgrade:   upgrade.append((pkg.name, pkg.candidate.version))
    output = ''
    if len(delete) != 0:
        output += '\nDelete:%d: ' % len(delete)
        output += ' '.join(str(i[0])+'='+str(i[1]) for i in delete)
    elif len(downgrade) != 0:
        output += '\nDowngrade:%d: ' % len(downgrade)
        output += ' '.join(str(i[0])+'='+str(i[1]) for i in downgrade)
    elif len(install) != 0:
        output += '\nInstall:%d: ' % len(install)
        output += ' '.join(str(i[0])+'='+str(i[1]) for i in install)
    elif len(keep) != 0:
        output += '\nKeep:%d: ' % len(keep)
        output += ' '.join(str(i[0])+'='+str(i[1]) for i in keep)
    elif len(reinstall) != 0:
        output += '\nReinstall:%d: ' % len(reinstall)
        output += ' '.join(str(i[0])+'='+str(i[1]) for i in reinstall)
    elif len(upgrade) != 0:
        output += '\nUpgrade:%d: ' % len(upgrade)
        output += ' '.join(str(i[0])+'='+str(i[1]) for i in upgrade)
    return output


def mark_changes(package_list, cache):
    """Mark changes from list in cache"""
    # packlage_list = {'name': {'version': 'x', 'resolved': False}}
    debug('mark_changes()')
    for k,v in package_list.iteritems():
        if v['version'] is not None and v['version'] != '':
            if v['version'] not in cache[k].versions:
                die('Could not find %s version %s in cache' % (k, v['version']))
            debug('change cache: candidate %s=%s' % (k, v['version']))
            cache[k].candidate = cache[k].versions[v['version']]
        debug('cache[%s].mark_install' % k)
        cache[k].mark_install(auto_fix=False)
    resolver = apt.cache.ProblemResolver(cache)
    try:
        resolver.resolve()
    except Exception, e:
        die('Failed to resolve conflicts: %s' % str(e))


def resolve_deps(package_name, package_list, cache):
    """Resolve package dependencies and add them to package_list
    package_name indicates entry in package_list"""
    debug('resolve_deps(%s)' % package_name)

    # Check correct call
    if package_list[package_name]['resolved']:
        debug('resolve_deps incorrect call: package %s already resolved' % package_name)
        return

    # Virtual package - do not mess with it, let apt think
    if package_name not in cache:
        providing = [ i.name for i in cache.get_providing_packages(package_name) ]
        if len(providing) == 0:
            die('error in resolve_deps: %s is virtual package and no one can provide it' % package_name)
        else:
            debug('virtual package %s - will not be checked futher' % package_name)
            package_list[package_name]['resolved'] = True
            return

    package_props = package_list[package_name]
    pkg = cache[package_name]

    # No version given - don't mess with it, let apt think
    if package_props['version'] is None or package_props['version'] == '':
        # debug('no explicit version required for %s - will not be checked futher' % package_name)
        # package_list[package_name]['resolved'] = True
        debug('no explicit version required for %s - will use candidate version' % package_name)
        ver = pkg.candidate.version

    # Explicit version given - let's resolve it
    if package_props['version'] in pkg.versions.keys():
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
                debug('already installed: %s' % bdep.name)
                # Found installed dependency for which we need precise version
                if bdep.relation == '=':
                    package_list[bdep.name] = {'version': bdep.version, 'resolved': bdep_resolved}
                    debug('added dependency with excplicit version: %s=%s' % (bdep.name, bdep.version))
                else:
                    # package_list[bdep.name] = {'version': None, 'resolved': bdep_resolved}
                    debug('found dependency without explicit version - do not add: %s' % bdep.name)
                dep_resolved = True
                break

        # No already installed variants found - get first
        # If precise version required - handle it
        if not dep_resolved:
            debug('not installed: %s' % bdep.name)
            bdep = dep.or_dependencies.pop()

            if bdep.name in package_list:
                bdep_resolved = package_list[bdep.name]['resolved']
            else:
                bdep_resolved = False

            if bdep.relation == '=':
                package_list[bdep.name] = {'version': bdep.version, 'resolved': bdep_resolved}
                debug('added dependency with excplicit version: %s=%s' % (bdep.name, bdep.version))
            else:
                # package_list[bdep.name] = {'version': None, 'resolved': bdep_resolved}
                debug('found dependency without explicit version - do not add: %s' % bdep.name)

    package_list[package_name]['resolved'] = True
    # // resolve_deps


def resolve_all(cache, packages, ACTION, FORCE):
    '''Resolve dependencies for everything in packages'''

    orig_packages=packages.copy()

    # Clean from already installed for 'install-only-new'
    if ACTION in ('install-only-new', 'resolve-only-new'):
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
    # Clear list from already installed packages without explicit versions
    tmp = {k:v for (k,v) in packages.iteritems() if k in cache and ( cache[k].installed is None or v['version'] is not None ) }
    packages=tmp
    debug('# packages after first cleanup: %d' % len(packages))
    # Clear list from already installed packages with necessary version
    # TODO
    tmp = {k:v for (k,v) in packages.iteritems() if k in cache and not ( cache[k].installed is not None and cache[k].installed.version == v['version'] ) }
    packages=tmp
    debug('# packages after second cleanup: %d' % len(packages))

    debug('result: \n' + pformat(packages))


def main(cache, packages, ACTION, FORCE):
    '''main action, specified by options'''
    # Already installed packages excluded from list for 'install-only-new', so actions are similar
    if ACTION in ('install', 'install-only-new'):

        changes={}
        print report_changes(cache, changes)

        if cache.broken_count != 0:
            die('Broken packages: %d' % cache.broken_count)

        if cache.dpkg_journal_dirty:
            die('dpkg was interrupted. Try to fix: dpkg --configure -a')

        if len(changes['delete']) != 0:
            if not FORCE:
                die('Need to delete some packages to proceed - abort')
            else:
                debug('Run commit first time - to delete packages')
                cache.commit()
                mark_changes(packages, cache)

        try:
            cache.fetch_archives()
        except Exception, e:
            die('Failed to fetch archives: %s' % str(e))

        try:
            cache.commit()
        except Exception, e:
            die('Failed to commit changes: %s' % str(e))

    elif ACTION in ('resolve', 'resolve-only-new'):
        print report_changes(cache)
    else:
        parser.print_usage()
        die('Unknown action %s' % ACTION)


# Options

LOOP_LIMIT = 10000

    if __name__ == '__main__':

    # Parse command-line arguments
    parser = OptionParser(usage='Usage: %prog [options] install|install-only-new|resolve|resolve-only-new pkg1=version1 pkg2 ...')
    parser.add_option('--debug', action='store_true', dest='DEBUG', default=False, help='Enable debugging')
    parser.add_option('-f', '--force-delete', dest='FORCE', default=False, help='Delete packages if necessary')
    #parser.add_option('-t', '--target-release', dest='TARGET', help='Do all actions without confirmation')

    options, args = parser.parse_args()
    if len(args) < 2:
        parser.print_help()
        die('Too few arguments')

    ACTION = args[0]
    if ACTION not in ('install', 'install-only-new', 'resolve', 'resolve-only-new'):
        parser.print_help()
        die('Invalid argument %s')

    DEBUG = options.DEBUG
    FORCE = options.FORCE
    # TARGET = options.TARGET

    # {'name': {'version': 'x', 'resolved': False}}
    packages = {}

    for i in args[1:]:
        if '=' not in i:
            packages[i] = {'version': None, 'resolved': False}
        else:
            packages[i.split('=')[0]] = {'version': i.split('=')[1], 'resolved': False}

    # Initilize apt cache interface
    cache = apt.cache.Cache()

    # Resolve dependencies and store in packages
    resolve_all(packages, cache, ACTION, FORCE)

    mark_changes(packages, cache)

    # Perform specified ACTION
    main(packages, cache, ACTION, FORCE)

    sys.exit(0)
