# Klever Documentation

You can find Klever documentation online at http://klever.readthedocs.io or
build it yourself. It contains deployment instructions, tutorial and some
instructions for developers. We plan to incorporate other user documentation
directly into the Klever web interface.

To build Klever documentation you need:
* Install Python 3.4 or higher (https://www.python.org/).
* Install Sphinx (http://sphinx-doc.org) and its theme Read the Docs
  (https://sphinx-rtd-theme.readthedocs.io/en/latest/), e.g.:
    pip3 install sphinx sphinx_rtd_theme
* Execute the following command from the source tree root directory (it should
  be executed each time when documentation might be changed):
    make -C docs html
Then you can open generated documentation index "docs/_build/html/index.html"
in a web browser.
