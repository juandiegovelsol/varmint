Tux.use_scripting_controller(true);
function press(c) { Tux.do_scripting_controller(c, true); }
function rel(c) { Tux.do_scripting_controller(c, false); }
function tap(c, n) { for (local i = 0; i < n; i += 1) { press(c); wait(0.03); rel(c); wait(0.16); } }
function hold(c, t) { press(c); wait(t); rel(c); }
wait(9.0);
press("action");
tap("right", 5);
wait(0.6);
rel("action");
wait(2.4);
press("action");
tap("left", 8);
wait(0.6);
tap("left", 7);
wait(0.8);
rel("action");
wait(2.0);
tap("right", 20);
wait(1.5);
hold("left", 1.6);
wait(0.8);
press("jump"); wait(0.05); press("right"); wait(0.2); rel("right"); wait(0.15); rel("jump");
wait(1.8);
hold("left", 0.35);
wait(0.8);
press("action"); press("right"); wait(0.9); rel("action"); wait(0.1); rel("right");
wait(3.0);
