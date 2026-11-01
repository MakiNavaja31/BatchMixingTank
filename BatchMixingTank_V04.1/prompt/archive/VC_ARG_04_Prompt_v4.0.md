
## V04 01.Nov.2026

Acting as an industrial process automation and simulation, IIoT and HMI expert, with focus in the operatio of a Batch mixer tank, described in the specification 'VC_ARG_04_Operation_specification_v4.0' (valves, sensors, actuators, protocols will be discussed futher), guide me in the following purpose. Analyze each proposal, advise and propose me improvements/modifications, before acting 

The attached 'VC_ARG_04_Operation_specification_v4.0' is the specification,the single source of truth: read it completely before doing anything. Attached inputs: the recipes file (sheet `recipes`), the production orders file (sheet `today`) and the empty Production Order Report template.

1. Simulated clock starts at [06:30:00 CET]

**Tasks**
2. Tell me what you find before simulating: recipe percentages add up to 100, approved flags, recipe IDs used by the orders exist and are approved, volumes are integers from 20 to 100, Batch IDs are text. Apply only the corrections I list. If something blocks the run, ask me; otherwise state what you assumed and go on.
3. **Build the simulator** in Python with a 100 ms tick, strictly following the specification: rates, state machine (T1 to T18), alarms 1 to 5 with the relative tolerance and the progress monitor, scrap, partial batch, cleaning rules, operator rules. Do not invent behaviour. Where the specification is silent, choose the simplest reasonable default and list it under Assumptions.
4.**Run the scenario** with the operator model of section 13 (random reaction 3–8 s, seed 7; faults injected 0.5 s after a batch becomes pending).
5. **Fill the report template.** Keep its look and columns. Header VC_ARG_03. Sheet `today` (one row per order, repeats appended with `Retry of #m`, scrap in Remarks), sheet `Events` (every command, fault, state change, alarm and refusal), sheet `Test results` (scenario, specification expectation, observed, PASS/FAIL/OBSERVATION). Fill the summary values that come from the run (cleanings completed, scrap generated).
6. **Build the dashboard** described in section 12, headed VC_ARG_04, labelled as simulated data. Use the Dashboard artifact type if it is available, otherwise one self-contained HTML page. Every number must come from the simulation data.
7. **Write the raw log** as CSV at 5 s resolution (state, sub-step, product, level, outputs, alarm, batch index, report row, scrap total).
8. **Verify before you hand over:** recompute the totals (rows, completed, aborted, litres produced, scrap, cleanings, alarms by code) directly from the rows and the events and make sure the report, the dashboard and your summary agree; the level never exceeds the overflow limit by more than one tick of flow; every PASS in the test sheet is backed by a check in the code, not by a hard-coded sentence.

**Deliver**
9. `VC_ARG_04_Production_Orders_Report.xlsx`, `VC_ARG_04_sim_log_5s.csv`, the dashboard, and the production order list used.
10. **Generate an industrial dashboard** create a HMI-like representing the process, I want a single view "Batch Mixing Tank" in a 16:9 horizontalspect ratio and set up for recording in Full HD. Use a clear, clean, and slightly futuristic industrial aesthetic, with a bluish-gray background, white panels, Roboto font, and blue and orange accents. Consider the follwing in the **layout**, ensure that most relavant information, status, alarms, etc are included.
 - On the right, depict the 100-liter tank, with a level ranging from 0 to 100 percent and a mark for the received setpoint. Include the pipes, the inlet and outlet valves, and the agitator. Its indicators and animations should depend on the received readings and be accompanied by text, so as not to rely
solely on color
 - On the left, display the target level and the mixing time. The level will accept values between 30 and 80 percent; the time, whole numbers between 5 and 20 seconds. The initial setpoints will be 60 percent and 5 seconds. They can only be edited when the system is idle, and each will have its own "Send" button.
- Header left: include the logo attached "Maki+Pope.png" with the credit '© del Maestro IvÁ'in 10px
- Footer left: include 'Created by Ángel Rodríguez + Claude Opus 5.5 (cc)''

**Style:** English, concise, no filler. Ask at most the questions that block the work.

