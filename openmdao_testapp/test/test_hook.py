import json

from argparse import ArgumentParser

def send_payload():
    parser = ArgumentParser()
    parser.add_argument('-c', '--commit', action='store', type=str,
                        dest='commit_id', 
                        default='ef7189b7b8dbc040df7c87c12f63ccd80bd1a8f2',
                        help='id of commit to test')
    parser.add_argument('-r', '--repo', action='store', type=str,
                        dest='repo', 
                        default='http://github.com/OpenMDAO/OpenMDAO-Framework',
                        help='repo url')
    parser.add_argument('-b', '--branch', action='store', type=str,
                        dest='branch', 
                        default='refs/heads/dev',
                        help='branch name')
    
    options = parser.parse_args()

    payload = {
        "repository": {
          "url": options.repo,
        },
        "after": options.commit_id,
        "ref": options.branch,
      }
    
    print json.dumps(payload)
    