import optparse
import paramiko
import tempfile
import urllib2
import ssl
import httplib
import json
import os

parser = optparse.OptionParser()
parser.add_option('--hosts', dest="hosts", type="string", help="Comma separated list of hosts to update")

std_login = 'root'
std_pass = '1q2w3e'

def copy_poa_certificate(host_name):
    transport = paramiko.Transport((host_name, 22))
    transport.connect(username=std_login, password=std_pass)
    sftp = paramiko.SFTPClient.from_transport(transport)
    temp_file_name = tempfile.mktemp('.pem')
    sftp.get('/usr/local/pem/APS/certificates/poa.pem', temp_file_name)
    return temp_file_name

def send_directory(source, target, host_name):
    transport = paramiko.Transport((host_name, 22))
    transport.connect(username=std_login, password=std_pass)
    sftp = paramiko.SFTPClient.from_transport(transport)
    for dirpath, _, filenames in os.walk(source):
        path = dirpath[len(source):len(dirpath)]
        for filename in filenames:
            source_file = dirpath + "/" + filename
            target_file = target + path + "/" + filename
            sftp.put(source_file, target_file)    

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
    cert_file = copy_poa_certificate(options.hosts)
    get_aps_packages_url = "https://%s:6308/aps/2/packages" % host_name
    opener = urllib2.build_opener(HTTPS_OPENER(cert_file, cert_file))
    response = opener.open(get_aps_packages_url).read()
    return json.loads(response)

def find_package_uid(host_name, app_name):
    packages = get_aps_packages(options.hosts)
    for package in packages:
        if package['name'] == app_name:
            return package['aps']['id']
    raise Exception("Couldn't find a package for application with name '%s' on host '%s'" % (app_name, host_name))

if __name__ == "__main__":
    (options, args) = parser.parse_args()
    print options.hosts
    package_uid = find_package_uid(options.hosts, 'APS Init Wizard')
    send_directory("/home/anton/dev/osa/modules/platform/cells/js-ui/aps_init_wizard/application/src/ui", "/usr/local/pem/APS/packages/" + package_uid + "/ui/", options.hosts)
    print package_uid


# to hosts-list
# to spconfig - auto find hosts
# from directory in js-ui - fetch app name
# loop - store keys, remember package names, repeat copy on command

