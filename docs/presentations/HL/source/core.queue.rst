``ResourceQueue``
-----------------

A job priority queue

.. raw:: html

   <div style="display:flex; justify-content:center;">
     <svg style="display:block;" width="980" height="400" viewBox="0 0 980 440" xmlns="http://www.w3.org/2000/svg">
       <defs>
         <style>
           .jobbox { fill: rgba(255,255,255,0.06); stroke: rgba(255,255,255,0.55); stroke-width: 2; }
           .queue  { fill: transparent; stroke: rgba(255,255,255,0.70); stroke-width: 2; }
           .cell   { fill: rgba(255,255,255,0.04); stroke: rgba(255,255,255,0.35); stroke-width: 2; }
           .label  { fill: rgba(255,255,255,0.92); font: 26px ui-monospace, Menlo, Consolas, monospace; }
           .title  { fill: rgba(255,255,255,0.92); font: 20px ui-monospace, Menlo, Consolas, monospace; }
           .conn   { fill: none; stroke: rgba(255,255,255,0.75); stroke-width: 3; }
         </style>

         <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5"
                 markerWidth="5" markerHeight="5" orient="auto">
           <path d="M 0 0 L 10 5 L 0 10 z" fill="rgba(255,255,255,0.75)"/>
         </marker>
       </defs>

       <!-- scale down vertically a bit more (overall height ~10% less than before) -->
       <g transform="translate(0, 28) scale(1, 0.82)">

         <!-- ResourceQueue -->
         <text class="title" x="500" y="155" text-anchor="middle"></text>
         <rect class="queue" x="276" y="170" width="448" height="132" rx="14" />

         <!-- Cells -->
         <rect class="cell" x="292" y="198" width="128" height="76" rx="10" />
         <rect class="cell" x="436" y="198" width="128" height="76" rx="10" />
         <rect class="cell" x="580" y="198" width="128" height="76" rx="10" />

         <text class="label" x="356" y="247" text-anchor="middle">$</text>
         <text class="label" x="500" y="247" text-anchor="middle">$$</text>
         <text class="label" x="644" y="247" text-anchor="middle">$$$</text>

         <!-- Jobs moved closer laterally (keep symmetry) -->
         <!-- queue left edge = 276, job width = 150, gap = 25 => job x = 101 -->
         <rect class="jobbox" x="101" y="70" width="150" height="70" rx="10" />
         <text class="label" x="176" y="115" text-anchor="middle"></text>

         <!-- queue right edge = 724, gap = 25 => job x = 749 -->
         <rect class="jobbox" x="749" y="332" width="150" height="70" rx="10" />
         <text class="label" x="824" y="377" text-anchor="middle"></text>

         <!-- Connectors (terminate/emit at queue border) -->
         <path class="conn" marker-end="url(#arrow)"
               d="M 176 140 L 176 236 L 276 236" />

         <path class="conn" marker-end="url(#arrow)"
               d="M 724 236 L 824 236 L 824 332" />

       </g>
     </svg>
   </div>

.. revealjs-fragments::

   * Jobs ordered by **cost**.
   * Highest cost *runnable* out first.


.. revealjs-break::
   :data-transition: none

.. raw:: html

   <div style="display:flex; justify-content:center;">
     <svg style="display:block;" width="980" height="400" viewBox="0 0 980 440" xmlns="http://www.w3.org/2000/svg">
       <defs>
         <style>
           .jobbox { fill: rgba(255,255,255,0.06); stroke: rgba(255,255,255,0.55); stroke-width: 2; }
           .queue  { fill: transparent; stroke: rgba(255,255,255,0.70); stroke-width: 2; }
           .cell   { fill: rgba(255,255,255,0.04); stroke: rgba(255,255,255,0.35); stroke-width: 2; }
           .label  { fill: rgba(255,255,255,0.92); font: 26px ui-monospace, Menlo, Consolas, monospace; }
           .title  { fill: rgba(255,255,255,0.92); font: 20px ui-monospace, Menlo, Consolas, monospace; }
           .conn   { fill: none; stroke: rgba(255,255,255,0.75); stroke-width: 3; }
         </style>

         <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5"
                 markerWidth="5" markerHeight="5" orient="auto">
           <path d="M 0 0 L 10 5 L 0 10 z" fill="rgba(255,255,255,0.75)"/>
         </marker>
       </defs>

       <!-- scale down vertically a bit more (overall height ~10% less than before) -->
       <g transform="translate(0, 28) scale(1, 0.82)">

         <!-- ResourceQueue -->
         <text class="title" x="500" y="155" text-anchor="middle"></text>
         <rect class="queue" x="276" y="170" width="448" height="132" rx="14" />

         <!-- Cells -->
         <rect class="cell" x="292" y="198" width="128" height="76" rx="10" />
         <rect class="cell" x="436" y="198" width="128" height="76" rx="10" />
         <rect class="cell" x="580" y="198" width="128" height="76" rx="10" />

         <text class="label" x="356" y="247" text-anchor="middle">$</text>
         <text class="label" x="500" y="247" text-anchor="middle">$$</text>
         <text class="label" x="644" y="247" text-anchor="middle">$$$</text>

         <!-- Jobs moved closer laterally (keep symmetry) -->
         <!-- queue left edge = 276, job width = 150, gap = 25 => job x = 101 -->
         <rect class="jobbox" x="101" y="70" width="150" height="70" rx="10" />
         <text class="label" x="176" y="115" text-anchor="middle"></text>

         <!-- queue right edge = 724, gap = 25 => job x = 749 -->
         <rect class="jobbox" x="749" y="332" width="150" height="70" rx="10" />
         <text class="label" x="824" y="377" text-anchor="middle"></text>

         <!-- Connectors (terminate/emit at queue border) -->
         <path class="conn" marker-end="url(#arrow)"
               d="M 176 140 L 176 236 L 276 236" />

         <path class="conn" marker-end="url(#arrow)"
               d="M 724 236 L 824 236 L 824 332" />

       </g>
     </svg>
   </div>

:math:`\mathrm{cost} = \sqrt{\sum_i r_i^2}`
