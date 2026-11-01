Batch Mixing Tank is a Vibe Coding Industrial experiment (Digitalización Férriz). It takes a 100 L batch mixing tank from a written operation specification to a tested digital twin, built together with Claude Opus 5.5.

The specification is the single source of truth. From it, a Python simulator (100 ms tick) runs a full simulated production day of 56 batches with injected faults: overflow, fill deviation, blocked valves, emergency and normal stops, and batches that aren’t allowed to run. The run produces:

a filled Production Order Report, with an event log and automatic PASS/FAIL tests;
a 5 s process log;
an operator HMI that replays the run in Full HD;
an analytics dashboard.

Every number is simulated data, and every result can be reproduced from the inputs in this repository.

<img width="1920" height="1080" alt="HMI_10_list_complete" src="https://github.com/user-attachments/assets/e0de4dd9-1395-44fa-90c1-bf10d489759a" />
