# VC_ARG_04 · Prompt v4.1 (01.Nov.2026)

Acting as an industrial process automation and simulation, IIoT and HMI expert, focused on the operation of the batch mixing tank described in `VC_ARG_04_Operation_Specification_v4.1` (valves, sensors, actuators and protocols will be discussed further), guide me in the following purpose. Analyze each proposal, advise and propose improvements or modifications before acting.

`VC_ARG_04_Operation_Specification_v4.1` is the specification and the single source of truth: read it completely before doing anything. Section numbers below refer to v4.1.

**Inputs**

- Recipes: `VC_ARG_03_Recipes_Template.xlsx`, sheet `recipes`.
- Production orders: `VC_ARG_03_Production_Orders_Template.xlsx`, sheet `today`.
- Report template: `VC_ARG_03_Production_Order_Report_Template.xlsx` (empty).
- Logo: `MakiPope.png`.

**Working agreement**

- "Analyze", "propose", "review", "what do you think": answer in chat only. "Write", "prepare", "generate", "run", "update": act.
- Never invent facts, APIs, file paths, versions or tool output. Mark claims as verified, inferred or unsure.
- Ask only the questions that block the work; for anything cheap to redo, state the assumption and go on.

## Tasks

1. **Simulated clock** starts at 06:30:00 CET on the run date.
2. **Check the data before simulating** (spec §4): recipe percentages add up to 100, recipe IDs, mixing times 5–600 s, approved flags; recipe IDs used by the orders exist; Batch IDs are text and unique; volumes are integers (20–100 L in the list, 40–100 L to run). Report what you find. Apply only the corrections I list. If something blocks the run, ask me; otherwise state what you assumed and go on.
3. **Rebalance the order list** (spec §4): apply the sub-batch rebalancing rule and save it as a new file with `Template` replaced by `REBALANCED` in the name. Single batches below 40 L stay as they are and raise alarm 6.
4. **Build the simulator** in Python with a 100 ms tick, strictly following the specification: rates, time-based dosing (§5 rule 13), state machine T1 to T20, alarms 1 to 6 with the tolerance and the progress monitor, scrap, partial batch, cancelled batch, cleaning rules and operator rules. Do not invent behaviour. Where the specification is silent, choose the simplest reasonable default and list it under Assumptions.
5. **Run the scenario** of spec §14: operator model with a random reaction of 3–8 s, seed 7; faults F1 to F10, each armed 0.5 s after its batch becomes pending.
6. **Fill the report template.** Keep its look and columns. Header VC_ARG_04. Sheet `today` (one row per order, repeats appended with `Retry of #m`, scrap in Remarks), sheet `Events` (every command, fault, state change, alarm and refusal, no row limit), sheet `Summary` (template values plus the v4 rows of §12, including the run values: cleanings completed, scrap generated), sheet `Legend` (SKIPPED and alarm 6), and a new sheet `Test results` (scenario, specification expectation, observed, PASS/FAIL/OBSERVATION).
7. **Build the analytics dashboard** of spec §13, headed VC_ARG_04 and labelled as simulated data. Use the Dashboard artifact type if it is available, otherwise one self-contained HTML page. Every number must come from the simulation data.
8. **Write the raw log** as CSV at 5 s resolution (state, sub-step, product, level, outputs, alarm, batch index, report row, scrap total).
9. **Build the HMI** "Batch Mixing Tank" (spec §11): a single 16:9 view designed at 1920 × 1080 for Full HD recording, replaying the simulation readings (one `estado` snapshot every 5 s) with play, speed, a timeline and a jump to the next alarm.
   - Look: clear, clean and slightly futuristic industrial aesthetic; bluish-grey background, white panels, Roboto, blue and orange accents.
   - Right: the 100 L tank with a 0–100 L scale (1 L = 1 %), the batch-volume setpoint marker (40 L during cleaning), the overflow limit, pipes, the four inlet and three outlet valves and the agitator. Indicators and animations depend on the readings and always carry text (OPEN, CLOSED, RUNNING, STOPPED), never colour alone. Cleaning liquid in a distinct colour.
   - Left: batch and operator commands per §11: next or current batch, volume entry (integer 40–100 L, editable only in Stopped or Waiting, repeat keeps the interrupted volume), the volume dialog, and the buttons Start, Normal Stop, Emergency Stop, Reset and Cancel batch enabled as in §11; dosing table; alarm field; counters.
   - Header left: the logo `MakiPope.png` with the credit `© del Maestro IvÁ` at 10 px.
   - Footer left: `Created by Ángel Rodríguez + Claude Opus 5.5 (cc)`. Footer right: `Emergency Stop is not a safety function`.
10. **Verify before you hand over:** recompute the totals (records, completed, aborted, skipped, litres produced, scrap, cleanings, alarms by code) directly from the rows and the events and make sure the report, the dashboard and your summary agree; the level never exceeds the overflow limit by more than one tick of flow; the outputs match §8 at every tick; every PASS in the test sheet is backed by a check in the code, not by a hard-coded sentence.

## Deliver

- `VC_ARG_04_Production_Orders_Report.xlsx`
- `VC_ARG_04_sim_log_5s.csv`
- `VC_ARG_03_Production_Orders_REBALANCED.xlsx` (the production order list used)
- the analytics dashboard
- the HMI page `VC_ARG_04_HMI_Batch_Mixing_Tank.html`
- the simulator source code

**Style:** English, concise, no filler. Ask at most the questions that block the work.

## Changes from prompt v4.0

- Refers to specification v4.1; section numbers corrected (operator model §14, dashboard §13).
- State machine T1 to T20 and alarms 1 to 6 (v4.0 said T1 to T18 and alarms 1 to 5).
- Report header VC_ARG_04 (v4.0 said VC_ARG_03).
- Volume check split: 20–100 L in the list, 40–100 L to run; rebalancing step and REBALANCED file added.
- Fault scenario F1 to F10 now defined in spec §14.
- HMI left panel follows spec §11 (batch volume entry and the five command buttons) instead of a 30–80 % level and 5–20 s mixing-time setpoint, which contradicted the specification.
- Logo file name `MakiPope.png`; HMI and simulator source added to the deliverables.
