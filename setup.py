
from setuptools import setup

setup(name='openmdao_testapp',
      version='0.1',
      description="a webapp for branch testing of openmdao",
      license='Apache License, Version 2.0',
      packages=['openmdao_testapp'],
      include_package_data = True,
      install_requires=[
          'openmdao.devtools',
      ],
      entry_points = {
         "nose.plugins": [
             "coverage2 = nosecoverage2.cover2:Coverage2"
         ]
      },
   )


