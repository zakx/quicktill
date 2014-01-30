#!/usr/bin/env python

from distutils.core import setup

setup(name='quicktill',
      version='0.10.7',
      description='Quick till and stock control library',
      author='Stephen Early',
      author_email='steve@greenend.org.uk',
      url='https://github.com/sde1000/quicktill',
      packages=['quicktill','quicktill.tillweb'],
      package_data={'quicktill.tillweb':
                        ['static/tillweb/*.js','templates/tillweb/*.html']},
      scripts=['runtill'],
      )
