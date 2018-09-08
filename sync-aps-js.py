import optparse
import paramiko
import tempfile
import urllib2
import ssl
import httplib
import json
import os
import sys
import logging
import tarfile
from multiprocessing import Pool

LOG_FORMAT = "%(levelname)s %(asctime)s %(message)s"
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format=LOG_FORMAT)
log = logging.getLogger()

parser = optparse.OptionParser()
parser.add_option('--hosts', dest="hosts", type="string", help="Comma separated list of hosts to update")
parser.add_option('--app', dest="app", type="string", help="Application name to sync")

app_update = "/tmp/app-update.tar"
std_login = 'root'
std_pass = '1q2w3e'

def copy_poa_certificate(host_name):
    transport = paramiko.Transport((host_name, 22))
    transport.connect(username=std_login, password=std_pass)
    sftp = paramiko.SFTPClient.from_transport(transport)
    temp_file_name = tempfile.mktemp('.pem')
    sftp.get('/usr/local/pem/APS/certificates/poa.pem', temp_file_name)
    return temp_file_name

class HTTPS_OPENER (urllib2.HTTPSHandler):
    def __init__(self, key, cert):
        context = ssl._create_unverified_context()
        urllib2.HTTPSHandler.__init__(self, context=context)
        self.cert = cert
    def https_open(self, req):
        return self.do_open(self.getConnection, req, context=self._context)
    def getConnection(self, host, context=None, timeout=300):
        return httplib.HTTPSConnection(host, cert_file=self.cert, context=context)

def get_aps_packages(host_name):
    cert_file = copy_poa_certificate( host_name)
    get_aps_packages_url = "https://%s:6308/aps/2/packages" % host_name
    opener = urllib2.build_opener(HTTPS_OPENER(cert_file, cert_file))
    response = opener.open(get_aps_packages_url).read()
    return json.loads(response)

def find_package_uid(host_name, app_name):
    packages = get_aps_packages(host_name)
    for package in packages:
        if package['name'] == app_name:
            package_uid = package['aps']['id']
            log.info("Package uuid %s found for app '%s' on host '%s'" % (package_uid, app_name, host_name))
            return package_uid
    raise Exception("Couldn't find a package for application with name '%s' on host '%s'" % (app_name, host_name))

def update_host(tar, host_to_package_id, host_name):
    package_id = host_to_package_id[host_name]
    transport = paramiko.Transport((host_name, 22))
    transport.connect(username=std_login, password=std_pass)
    sftp = paramiko.SFTPClient.from_transport(transport)
    log.info("Syncing to host %s" % host_name)
    log.info("Copying files from %s to %s on host %s" % (tar, package_id, host_name))
    sftp.put(tar, app_update)
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host_name, 22, 'root', '1q2w3e')
    target = "/usr/local/pem/APS/packages/%s/" % package_id
    command = "tar -xvf %s -C %s" % (app_update, target)
    ssh.exec_command(command)
    log.info("All done here!")

def get_target_hosts(opts):
    if not opts.hosts and not opts.vm:
        raise Exception("Either list of hosts os spconfig VM id must be specified as target")
    if opts.hosts:
        return opts.hosts.split(",")

def update_hosts(app_name, source, host_to_package_id):
    log.info("Syncing to hosts %s" % hosts)
    tar = tarfile.open(app_update, "w")
    tar.add(source, "ui")
    tar.close()
    pool = Pool(processes=10)
    asyncs = []
    for host in host_to_package_id:
        asyncs.append(pool.apply_async(update_host, (app_update, host_to_package_id, host)))
    for async in asyncs:
        async.wait(10000)        

def update_hosts_error(err):
    log.error("Host update failed: %s" % err)

if __name__ == "__main__":
    (opts, args) = parser.parse_args()
    app_name = opts.app
    hosts = get_target_hosts(opts)
    host_to_package_id = {}
    for host in hosts:
        package_uid = find_package_uid(host, app_name)
        host_to_package_id[host] = package_uid
    while True:
        print "Press Enter to sync '%s' app to following hosts:\n%s" % (app_name, "\n".join(hosts))
        cmd = raw_input()
        if cmd == "quit":
            exit(0)
        update_hosts(app_name, "/home/anton/dev/osa/modules/platform/cells/js-ui/aps_init_wizard/application/src/ui", host_to_package_id)
        print "\n"

# 1 from directory in js-ui - fetch app name
# 2 to spconfig - auto find hosts
# 3 logs, refactoring
