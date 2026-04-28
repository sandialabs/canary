Setting the stage
-----------------

.. container:: clutter-grid

   .. figure:: _static/alegra.png

   .. figure:: _static/comp-sim-sm.png

   .. figure:: _static/ramses.png

   .. figure:: _static/nvtest.png

   .. figure:: _static/testrun.png

   .. figure:: _static/vvtest.png

   .. figure:: _static/ctest.png

   .. figure:: _static/shellscript.png

   .. figure:: _static/gitlab.svg

.. revealjs-break::
   :notitle:

.. image:: _static/dollar.jpg
   :align: center
   :width: 30%

.. revealjs-fragments::

  * duplicated engineering effort;
  * inconsistent workflows; and
  * harder sharing of infrastructure (selection, reporting, CI, triage).

.. revealjs-break::
   :notitle:

.. figure:: _static/nvtest.png
   :class: fade-in

.. revealjs-break::
   :notitle:

.. figure:: _static/icon2.tiff
   :class: fade-in

.. revealjs-break::
   :notitle:

.. container:: two-up

   .. image:: _static/pluggy.png
      :width: 60%

   .. image:: _static/icon2.tiff
      :width: 60%

Canary was chosen due to being built on top of pluggy - a plugin framework that allows us to dynamically alter runtime behavior.
