Canary is
---------

.. revealjs-fragments::

  * an asynchronous job execution tool
  * fast, scalable, and portable from laptops to HPC
  * designed for **testing** scientific applications
  * but, well suited for engineering workflows
  * installable today::

      pip install canary-wm


Typical usage
^^^^^^^^^^^^^

.. raw:: html

   <div style="display:flex; justify-content:center;">
     <svg width="980" height="500" viewBox="0 0 980 500" xmlns="http://www.w3.org/2000/svg">
       <defs>
         <style>
           .node  { fill: rgba(255,255,255,0.06); stroke: rgba(255,255,255,0.60); stroke-width: 2; }
           .label { fill: rgba(255,255,255,0.92); font: 20px ui-monospace, Menlo, Consolas, monospace; }
           .conn  { fill: none; stroke: rgba(255,255,255,0.70); stroke-width: 3; }
         </style>

         <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5"
                 markerWidth="2.6" markerHeight="2.6" orient="auto">
           <path d="M 0 0 L 10 5 L 0 10 z" fill="rgba(255,255,255,0.70)"/>
         </marker>
       </defs>

       <!-- layout constants:
            node width = 300, x = 340
            node height = 64
            gap = 34  (increased from 22)
            centers: y_center = y + 32
       -->

       <!-- Nodes -->
       <rect class="node" x="340" y="20" width="300" height="64" rx="10"/>
       <text class="label" x="490" y="60" text-anchor="middle" dominant-baseline="middle">
         <tspan x="490" dy="0">$ canary run PATHS</tspan>
       </text>

       <rect class="node" x="340" y="118" width="300" height="64" rx="10"/>
       <text class="label" x="490" y="155" text-anchor="middle" dominant-baseline="middle">
         <tspan x="490" dy="-11">Scan PATHS for</tspan>
         <tspan x="490" dy="22">test generators</tspan>
       </text>

       <rect class="node" x="340" y="216" width="300" height="64" rx="10"/>
       <text class="label" x="490" y="255" text-anchor="middle" dominant-baseline="middle">
         <tspan x="490" dy="0">Generate test cases</tspan>
       </text>

       <rect class="node" x="340" y="314" width="300" height="64" rx="10"/>
       <text class="label" x="490" y="352" text-anchor="middle" dominant-baseline="middle">
         <tspan x="490" dy="-11">Run test cases</tspan>
         <tspan x="490" dy="22">asynchronously</tspan>
       </text>

       <rect class="node" x="340" y="412" width="300" height="64" rx="10"/>
       <text class="label" x="490" y="450" text-anchor="middle" dominant-baseline="middle">
         <tspan x="490" dy="0">Report results</tspan>
       </text>

       <!-- Connectors (recomputed for new y positions) -->
       <path class="conn" marker-end="url(#arrow)" d="M 490 84  L 490 118" />
       <path class="conn" marker-end="url(#arrow)" d="M 490 182 L 490 216" />
       <path class="conn" marker-end="url(#arrow)" d="M 490 280 L 490 314" />
       <path class="conn" marker-end="url(#arrow)" d="M 490 378 L 490 412" />
     </svg>
   </div>
