# MINDSET_FTT_Power

FTT:Power is run through MSET. Select its input scenario with `ftt_p_scenario`
in the MSET run `.ini` file; `ftt_run` independently controls whether the module
is enabled. If the setting is omitted, the run defaults to `S0`. A configured
scenario without a matching `Inputs/<scenario>` directory logs a warning and
uses the `S0` inputs as its baseline.
