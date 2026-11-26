# MINDSET_FTT_Power

FTT:Power is run through MSET. Set `ftt_p_scenario` in the MSET run `.ini` to
select its input scenario; `ftt_p_run` controls whether Power is enabled.
FTT:Transport uses `ftt_tr_scenario` to select its inputs, while `ftt_tr_run`
controls whether Transport is enabled. Both scenario settings default to `S0`.

If a selected non-`S0` scenario has no input CSVs, the model logs a warning and
uses the `S0` inputs as its baseline. Power inputs are read from
`MINDSET_FTT_Power/Inputs/<scenario>`; Transport inputs are read from
`MINDSET_FTT_Power/FTT-Tr-Inputs/Inputs/<scenario>`.
