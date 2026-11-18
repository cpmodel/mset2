Settings files
==============

A run of MSET is controlled by a settings file. These files use the ``.ini`` 
format. Each run of the model specifies information such as the scenario name, 
the start and end years, and whether to calibrate the model.

Common settings
---------------

.. code:: text

   [settings]
   scenario_name = empty
   model_start = 2019
   model_end = 2030
   CALIBRATING = False
   ftt_run = False

``scenario_name``
   The name of the scenario Excel file in ``Data/MSET_data/Scenarios``. You do
   not need to include the ``.xlsx`` part.

``model_start`` and ``model_end``
   The first and last years of the run. Both years are included.

``CALIBRATING``
   If ``True``, the model creates new residuals to fit projected output and
   saves the residuals for later runs. If ``False``, the model loads saved 
   ``.pkl`` residuals from the ``Residuals`` folder.

``ftt_run``
   If ``True``, the model uses the FTT:Power electricity sub-model. Only use 
   this when the FTT settings and input files are available. FTT can be called
   as a package using PyPI. It can be installed with the command 
   ``pip install future-technology-transformation``.

``mrio_inverse_recalculate``
   If ``True``, the model rebuilds the input-output matrices at the start of the
   run.

Convergence settings
--------------------

These settings control when the within-year loop can stop:

.. code:: text

   COND_LABOR = 5
   COND_TAX = 5
   COND_TRADE = 5
   COND_PRICE = 5
   ITER_MAX = 100

The ``COND_`` values are percentage thresholds for convergence. 
See :doc:`model_solving` for more detail.

``ITER_MAX`` is the maximum number of within-year iterations. Reaching this 
limit does not necessarily mean the model has converged.