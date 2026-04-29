``ResourceQueue``
-----------------

.. image:: _static/queue.png
   :align: center
   :width: 60%

.. revealjs-fragments::

   * Jobs are ordered by **cost**.
   * Highest cost runs first (when resources allow).

.. revealjs-break::
   :data-transition: none

.. image:: _static/queue.png
   :align: center
   :width: 60%

.. math::

    \mathtt{cost} = \left\lVert \mathbf{r} \right\rVert_2 = \sqrt{\sum_{i=1}^{n} r_i^{2}}
