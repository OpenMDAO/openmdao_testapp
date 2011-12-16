import json
import urllib
import urllib2
from argparse import ArgumentParser

def send_payload():
    parser = ArgumentParser()
    parser.add_argument('-c', '--commit', action='store', type=str,
                        dest='commit_id', 
                        default='c5c3985214b1f7afe005bea73663bf6576b634c5',
                        help='id of commit to test')
    parser.add_argument('-r', '--repo', action='store', type=str,
                        dest='repo', 
                        default='https://github.com/OpenMDAO/OpenMDAO-Framework',
                        help='repo url')
    parser.add_argument('-b', '--branch', action='store', type=str,
                        dest='branch', 
                        default='refs/heads/dev',
                        help='branch name')
    
    parser.add_argument('-s', '--server', action='store', type=str,
                        dest='server', 
                        default='http://localhost:8888',
                        help='url:port of testapp server')
    
    options = parser.parse_args()

    payload = {
        "repository": {
          "url": options.repo,
        },
        "after": options.commit_id,
        "ref": options.branch,
      }
    
    print 'sending...'
    payload = json.dumps(payload)
    print payload
    
    server = options.server + '/p_r/run'
    reply = urllib2.urlopen(server, urllib.urlencode({'payload': payload}))
    
    print 'reply = ',reply.read()
    
    
    