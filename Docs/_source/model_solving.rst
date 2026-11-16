How MSET solves
===============

MSET is recursively dynamic: it solves one year at a time and carries
results into later years. There are two different kinds of
iteration within a year:

- **Calibration passes** adjust final-demand residuals to fit projected output
  when ``CALIBRATING`` is enabled.
- **Within-year iterations** recalculate linked economic variables until
  selected changes are small enough, or the iteration limit is reached.

The implementation is in ``ModelRun`` and ``initiate_modules``. The structure 
is:

.. code:: text

   for each model year:
       if calibrating:
           repeat calibration passes:
               run initiate_modules (including the within-year loop)
               compare output with the projection and adjust residuals
       else:
           run initiate_modules once (including the within-year loop)

       calculate results after the iterations
       if FTT is enabled: run FTT for this year once
       complete annual results and update variables for later years

Calibration passes
------------------

At the start of each year, ``solve_year`` initialises ``calibration_counter`` to
zero when calibration is enabled. Each pass calls ``initiate_modules`` and
compares its modeled output with the projection for that year:

.. code:: text

   projected output = previous-year output * projected output growth factor
   output residual  = projected output - previous-year output - dq_total

The calibration target is **gross output**, by region and sector.

The residual is set to zero for the configured cost-curve employment sectors
and wherever its absolute value is below 10. The code converts the remaining
output residual into a final-demand adjustment using ``calc_fd_vec``, a bounded
least-squares calculation using the Leontief matrix. It multiplies that
adjustment by 0.5 to damp oscillation, distributes it across household,
government and fixed-capital demand, and runs another pass. The next pass
applies the resulting residual as a demand shock.

Another pass is explicitly required by the code: the normal convergence 
condition requires ``calibration_counter > 0``. Therefore pass 0 cannot be 
accepted, even when its error is already within the thresholds.

When does calibration stop?
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Convergence requires both of these **hard-coded** conditions:

1. The maximum absolute regional aggregate error is less than 2%. For each
   region, this is the sum of its signed sector residuals divided by the sum
   of its projected sector outputs; sector errors can therefore offset.
2. The mean absolute sector-level relative error across region-sector entries
   is less than 10%. This is a mean, not a maximum for each sector.

If the maximum regional error worsens after pass 0, the code restores the
previous final-demand residuals, sets an error flag and runs another pass.
The error flag causes that next pass to exit regardless of whether the normal
thresholds are met. The counter is not incremented on this recovery path, and
the subsequent "Calibration done" message alone does not establish convergence.
The ``ITER_MAX`` variable set in ``settings.ini`` does not limit calibration 
passes.

Reusing residuals for scenario runs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Calibration is not required on every run. When ``CALIBRATING = False``, the
model loads ``Residuals/residuals_<year>.pkl`` for each year and applies the
saved final-demand residuals without rerunning the calibration loop. It calls
``initiate_modules`` once per year, still including the separate within-year
loop.

For example, after calibrating a baseline, a carbon-price scenario can be run
with calibration off. Residuals should come from a compatible baseline, 
including the same model inputs, regional aggregation and time period. 
Recalibration is required when the underlying baseline or model configuration 
changes materially. A non-empty residual file must exist for **every** model 
year.


Within-year iterations
----------------------

Within each call to ``initiate_modules``, the model first computes the year's
initial economic responses. If the within-year loop is enabled, it then
recalculates linked values including labor compensation, prices, demand, trade,
output and tax incidence. Its counter ``iter_run``, starts at 1 for **each
call** to ``initiate_modules``, and is separate from ``calibration_counter``.

Convergence criteria are specified in ``settings.ini``. The loop stops when all 
of the following hold:

+-----------------------------------+-----------------------------------+
| Setting                           | Check                             |
+===================================+===================================+
| ``COND_LABOR``                    | Labor compensation change is      |
|                                   | below the threshold.              |
+-----------------------------------+-----------------------------------+
| ``COND_TAX``                      | Tax-revenue change is below the   |
|                                   | threshold.                        |
+-----------------------------------+-----------------------------------+
| ``COND_PRICE``                    | The maximum change in ``dp_all``  |
|                                   | is below the threshold.           |
+-----------------------------------+-----------------------------------+
| ``COND_TRADE``                    | The old and new trade matrices    |
|                                   | pass ``numpy.allclose``, using    |
|                                   | this value as ``atol`` and        |
|                                   | NumPy's default relative          |
|                                   | tolerance.                        |
+-----------------------------------+-----------------------------------+

These settings are read as integers and divided by 100: for example, ``5``
becomes ``0.05``. The first iteration sets the labor, tax and price conditions
to infinity, so it normally cannot satisfy the convergence test.

The loop also stops when ``iter_run > ITER_MAX``. Reaching that limit is **not**
the same as satisfying the convergence criteria.