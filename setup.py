
from setuptools import setup

setup(name='openmdao_testapp',
      version='0.1',
      description="a webapp for branch testing of openmdao",
      license='Apache License, Version 2.0',
      packages=['openmdao_testapp'],
      include_package_data = True,
      install_requires=[
          'openmdao.devtools',
          'argparse',
          'web.py'
      ],
      entry_points = {
         "console_scripts": [
             "send_payload = openmdao_testapp.test.test_hook:send_payload"
             "start_server = openmdao_testapp.post_receive:start_server"
         ]
      },
   )


