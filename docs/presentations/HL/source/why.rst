Setting the stage
-----------------

.. container:: clutter-grid

   .. figure:: _static/alegra.png

   .. figure:: _static/comp-sim-sm.png

   .. figure:: _static/ramses.png

   .. raw:: html

      <div style="display:flex; justify-content:center; align-items:center; width:100%;">
        <div style="
          display: inline-block;
          font-size: 60px;
          line-height: 1.0;
          font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
          padding: 0.15em 0.35em;
          border-radius: 0.15em;
          background: rgba(255,255,255,0.08);
          border: 2px solid rgba(255,255,255,0.18);
        ">nvtest</div>
      </div>

   .. raw:: html

      <div style="display:flex; justify-content:center; align-items:center; width:100%;">
        <div style="
          display: inline-block;
          font-size: 60px;
          line-height: 1.0;
          font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
          padding: 0.15em 0.35em;
          border-radius: 0.15em;
          background: rgba(255,255,255,0.08);
          border: 2px solid rgba(255,255,255,0.18);
        ">testrun</div>
      </div>

   .. figure:: _static/vvtest.png

   .. figure:: _static/ctest.png

   .. figure:: _static/shellscript.png

   .. figure:: _static/gitlab.svg

.. revealjs-break::
   :notitle:

.. raw:: html

   <div style="font-size: 180px; line-height: 1;">\( \$\$\$ \)</div>

.. revealjs-fragments::

  * duplicated engineering effort;
  * inconsistent workflows; and
  * harder sharing of infrastructure (selection, reporting, CI, triage).

.. revealjs-break::
   :notitle:

.. raw:: html

   <div style="display: flex; justify-content: center; align-items: flex-start; padding-top: 5vh;">
     <div style="
       display: inline-block;
       font-size: 140px;
       line-height: 1.05;
       font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
       padding: 0.15em 0.35em;
       border-radius: 0.15em;
       background: rgba(255,255,255,0.08);
       border: 2px solid rgba(255,255,255,0.18);
     ">nvtest</div>
   </div>

``nvtest`` was chosen due to being built on top of `pluggy <https://github.com/pytest-dev/pluggy>`_ - a plugin framework that allows us to dynamically alter runtime behavior.

.. revealjs-break::
   :notitle:

.. figure:: _static/icon2.tiff
   :class: fade-in
