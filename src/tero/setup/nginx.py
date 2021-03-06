# Copyright (c) 2015, DjaoDjin inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
# THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
# PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
# CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS;
# OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
# WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR
# OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
# ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import os, re
from string import Template

from tero import APT_DISTRIBS, YUM_DISTRIBS, CONTEXT, setup
from tero.setup import modify_config


class nginxSetup(setup.SetupTemplate):

    http_config_template = """# internal node for %(app_name)s
#
# This config file is used for server behind a proxy front-end.
# We assume all traffic to it is somewhat legitimate. As a result,
# we do not have an actual domain name, nor block bots.

upstream proxy_%(app_name)s {
        server  127.0.0.1:8000;
}

server {
        listen          80 default_server;
        server_name     _;

        access_log /var/log/nginx/%(domain)s-access.log main;
        error_log  /var/log/nginx/%(domain)s-error.log;

        root %(document_root)s;

        location / {
            try_files /%(app_name)s$uri/index.html /%(app_name)s$uri.html /%(app_name)s$uri $uri/index.html $uri.html $uri @forward_to_%(app_name)s;
        }

        location @forward_to_%(app_name)s {
            include       /etc/nginx/proxy_params;
            proxy_pass    http://proxy_%(app_name)s;
        }

        error_page 500 502 503 504 /500.html;
        location = /50x.html {
            root %(document_root)s;
        }
}
"""

    https_config_template = """# whitelabel for %(app_name)s

upstream proxy_%(app_name)s {
        server  127.0.0.1:8000;
}

server {
        listen          80;
        server_name     %(domain)s *.%(domain)s;

        access_log /var/log/nginx/%(domain)s-access.log main;
        error_log  /var/log/nginx/%(domain)s-error.log;

        client_max_body_size 4G;
        keepalive_timeout 5;

        # Only requests to our Host are allowed
        if ($http_host !~* ^([a-zA-Z0-9-]+.)?%(domain)s$ ) {
            return 444;
        }

        # Block download user agents
        if ($http_user_agent ~* YoudaoBot|Sogou|YandexBot|linkdexbot) {
            return 403;
        }

        root %(document_root)s;

        location / {
            try_files /%(app_name)s$uri/index.html /%(app_name)s$uri.html /%(app_name)s$uri $uri/index.html $uri.html $uri @https-rewrite;
        }

        location @https-rewrite {
            return 301 https://$http_host$request_uri;
        }
}

# Forward to a canonical domain so that statistics are computed accurately.
server {
        listen       443;
        server_name  www.%(domain)s;

        ssl                  on;
        ssl_certificate      %(cert_path)s;
        ssl_certificate_key  %(key_path)s;
        ssl_ciphers "EECDH+AESGCM:EDH+AESGCM:AES256+EECDH:AES256+EDH";
        ssl_protocols TLSv1 TLSv1.1 TLSv1.2;
        ssl_dhparam /etc/ssl/certs/dhparam.pem;
        ssl_prefer_server_ciphers on;
        ssl_session_cache shared:SSL:10m;
        ssl_session_timeout  5m;

        location / {
            return 301 https://%(domain)s$request_uri;
        }
}

server {
        listen       443;
        server_name  *.%(domain)s;

        access_log /var/log/nginx/%(domain)s-access.log main;
        error_log  /var/log/nginx/%(domain)s-error.log;

        ssl                  on;
        ssl_certificate      %(wildcard_cert_path)s;
        ssl_certificate_key  %(wildcard_key_path)s;
        ssl_session_timeout  5m;
        ssl_ciphers "EECDH+AESGCM:EDH+AESGCM:AES256+EECDH:AES256+EDH";
        ssl_protocols TLSv1 TLSv1.1 TLSv1.2;
        ssl_dhparam /etc/ssl/certs/dhparam.pem;
        ssl_prefer_server_ciphers on;
        ssl_session_cache shared:SSL:10m;

        client_max_body_size 4G;
        keepalive_timeout 5;

        # Only requests to our Host are allowed
        if ($http_host !~* ^([a-zA-Z0-9-]+.)?%(domain)s$ ) {
            return 444;
        }

        # path for static files
        root %(document_root)s;

        location / {
            try_files /%(app_name)s$uri/index.html /%(app_name)s$uri.html /%(app_name)s$uri $uri/index.html $uri.html $uri @forward_to_%(app_name)s;
        }

        location @forward_to_%(app_name)s {
            include       /etc/nginx/proxy_params;
            proxy_pass    http://proxy_%(app_name)s;
        }

        error_page 500 502 503 504 /500.html;
        location = /50x.html {
            root %(document_root)s;
        }

}

server {
        listen       443;
        server_name  %(domain)s;

        access_log /var/log/nginx/%(domain)s-access.log main;
        error_log  /var/log/nginx/%(domain)s-error.log;

        ssl                  on;
        ssl_certificate      %(cert_path)s;
        ssl_certificate_key  %(key_path)s;
        ssl_ciphers "EECDH+AESGCM:EDH+AESGCM:AES256+EECDH:AES256+EDH";
        ssl_protocols TLSv1 TLSv1.1 TLSv1.2;
        ssl_dhparam /etc/ssl/certs/dhparam.pem;
        ssl_prefer_server_ciphers on;
        ssl_session_cache shared:SSL:10m;
        ssl_session_timeout  5m;

        client_max_body_size 4G;
        keepalive_timeout 5;

        # Only requests to our Host are allowed
        if ( $http_host !~* ^%(domain)s$ ) {
            return 444;
        }

        # Block download user agents
        if ($http_user_agent ~* YoudaoBot|Sogou|YandexBot|linkdexbot) {
            return 403;
        }

        # path for static files
        root %(document_root)s;

        location / {
            try_files /%(app_name)s$uri/index.html /%(app_name)s$uri.html /%(app_name)s$uri $uri/index.html $uri.html $uri @forward_to_%(app_name)s;
        }

        location @forward_to_%(app_name)s {
            include       /etc/nginx/proxy_params;
            proxy_pass    http://proxy_%(app_name)s;
        }

        error_page 500 502 503 504 /500.html;
        location = /50x.html {
            root %(document_root)s;
        }
}
"""

    proxy_params_template = """
            proxy_set_header X-Forwarded-For    $proxy_add_x_forwarded_for;
            proxy_set_header Host               $host;
            proxy_set_header X-Real-IP          $remote_addr;
            proxy_set_header X-Forwarded-Proto  $scheme;

            # proxy_redirect default;
            proxy_redirect off;
"""

    def __init__(self, name, files, **kwargs):
        super(nginxSetup, self).__init__(name, files, **kwargs)
        self.daemons = ['nginx']
        self.configfiles = []

    @staticmethod
    def conf_path(domain, dist_host, sysconfdir='/etc'):
        if dist_host in APT_DISTRIBS:
            return os.path.join(
                sysconfdir, 'nginx', 'sites-available', domain)
        elif dist_host in YUM_DISTRIBS:
            return os.path.join(
                sysconfdir, 'nginx', 'conf.d', domain + '.conf')

    def run(self, context):
        complete = super(nginxSetup, self).run(context)
        if not complete:
            # As long as the default setup cannot find all prerequisite
            # executable, libraries, etc. we cannot update configuration
            # files here.
            return complete

        remove_default_server = False
        for name, vals in self.files.iteritems():
            if name.startswith('site-config'):
                domain = None
                for elem in vals:
                    settings = elem[0]
                    if 'domainName' in settings:
                        domain = settings['domainName']
                    port = settings.get('port', '80')
                if port == '443':
                    self.site_conf(domain, context, self.https_config_template)
                else:
                    self.site_conf(domain, context, self.http_config_template)
                    remove_default_server = True

        # Remove default server otherwise our config for intermediate nodes
        # with no domain names will be overridden.
        if remove_default_server:
            org_nginx_conf, new_nginx_conf = setup.stageFile(os.path.join(
                context.SYSCONFDIR, 'nginx', 'nginx.conf'), context=context)
            with open(org_nginx_conf) as org_nginx_conf_file:
                with open(new_nginx_conf, 'w') as new_nginx_conf_file:
                    remove = 0
                    for line in org_nginx_conf_file.readlines():
                        look = re.match('.*server\s+{', line)
                        if look:
                            remove = 1
                        elif remove > 0:
                            look = re.match('{', line)
                            if look:
                                remove += 1
                            look = re.match('}', line)
                            if look:
                                remove -= 1
                        if remove == 0:
                            new_nginx_conf_file.write(line)

        certs_top = os.path.join(
            context.SYSCONFDIR, 'ssl', 'certs')
        dhparam_path = os.path.join(certs_top, 'dhparam.pem')
        setup.postinst.shellCommand([
            '[', '-f', dhparam_path, ']', '||', 'openssl', 'dhparam', '-out',
            dhparam_path, '4096'])
        setup.postinst.shellCommand([
            'setsebool', '-P', 'httpd_can_network_connect', '1'])
        setup.postinst.shellCommand(['systemctl', 'enable', 'nginx.service'])
        return complete


    def site_conf(self, domain, context, config_template):
        """
        Generate a configuration file for the site.
        """
        app_name =  domain.split('.')[0]
        document_root = os.path.join(
            os.sep, 'var', 'www', app_name, 'reps', app_name, 'htdocs')
        org_proxy_params, new_proxy_params = setup.stageFile(os.path.join(
            context.SYSCONFDIR, 'nginx', 'proxy_params'), context=context)
        with open(new_proxy_params, 'w') as proxy_params_file:
            proxy_params_file.write(self.proxy_params_template)

        certs_top = os.path.join(context.SYSCONFDIR, 'pki', 'tls', 'certs')
        key_top = os.path.join(context.SYSCONFDIR, 'pki', 'tls', 'private')
        key_path = os.path.join(key_top, '%s.key' % domain)
        cert_path = os.path.join(certs_top, '%s.crt' % domain)
        wildcard_key_path = os.path.join(key_top, 'wildcard-%s.key' % domain)
        wildcard_cert_path = os.path.join(certs_top, 'wildcard-%s.crt' % domain)
        org_site_conf, new_site_conf = setup.stageFile(self.conf_path(
            domain, context.host(), context.SYSCONFDIR), context=context)
        with open(new_site_conf, 'w') as site_conf_file:
            site_conf_file.write(config_template % {
                'app_name': app_name,
                'domain': domain,
                'document_root': document_root,
                'key_path': key_path,
                'cert_path': cert_path,
                'wildcard_key_path': wildcard_key_path,
                'wildcard_cert_path': wildcard_cert_path})
