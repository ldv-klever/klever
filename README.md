# Klever Documentation

The Klever documentation contains deployment instructions, tutorial, manuals for various use cases and some instructions
for developers.
You can find it online at http://klever.readthedocs.io or build it yourself.

To build the Klever documentation you need:
* Install [Python 3.4 or higher](https://www.python.org/).
* Install [Sphinx](http://sphinx-doc.org) and its
  [Read the Docs theme](https://sphinx-rtd-theme.readthedocs.io/en/latest/), e.g.:

      pip3 install sphinx sphinx_rtd_theme

  or in a more reliable way:

      pip3 install -r docs/requirements.txt

* Execute the following command from the source tree root directory (it should be executed each time when the
  documentation might be changed):

      make -C docs html

Then you can open generated documentation index "docs/_build/html/index.html" in a web browser.
