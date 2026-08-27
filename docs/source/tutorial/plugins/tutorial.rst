Using Plugins in Tutorials
===========================

This tutorial demonstrates how to use Canary plugins in documentation examples
by setting PYTHONPATH to include the tutorial directory.

Simple Plugin Example
---------------------

Here's a simple plugin that adds a custom hook:

.. literalinclude:: simple_plugin.py
   :language: python
   :caption: simple_plugin.py

Test Using the Plugin
---------------------

Here's a test that can use the plugin:

.. literalinclude:: plugin_example.pyt
   :language: python
   :caption: plugin_example.pyt

Running with Plugin Support
---------------------------

To run this example with the plugin, we set PYTHONPATH to include the plugin directory:

.. doc-run::
   :before_script: ['cp ${doc_source_dir}/plugin_example.pyt .', 'echo "PYTHONPATH will be: ${doc_source_dir}"']
   :script: ['python3 -c "import sys; print(\"PYTHONPATH is:\", sys.path)"', 'python3 -m canary -p simple_plugin run plugin_example.pyt']
   :env: {"PYTHONPATH": "${doc_source_dir}"}
   :display: command, stdout, stderr

How It Works
------------

1. **PYTHONPATH Expansion**: The `${doc_source_dir}` template variable expands to the directory containing the RST file
2. **Plugin Discovery**: Canary can now import `simple_plugin.py` because it's in the Python path
3. **Hook Registration**: The plugin registers its hooks when imported
4. **Execution**: The test runs with the plugin hooks available

Benefits of This Approach
--------------------------

- **No File Copying**: Plugins stay in their original location
- **Easy Maintenance**: Plugin code is right next to the tutorial that uses it
- **Real Execution**: Examples actually work during documentation build
- **No Core Changes**: Doesn't require modifying Canary's plugin manager

Advanced Plugin Example
-----------------------

For more complex plugins, you can create multiple files in the same directory:

.. code-block:: python
   :caption: advanced_plugin.py

   def canary_custom_hook():
       """Advanced plugin functionality."""
       return "advanced_result"

   def canary_addhooks(pluginmanager):
       pluginmanager.add_hook("canary_custom_hook", canary_custom_hook)

Then use it in tests with the same PYTHONPATH approach.

.. note::
   
   This approach works for most plugin scenarios in tutorials. For production use,
   consider proper plugin packaging and installation.
