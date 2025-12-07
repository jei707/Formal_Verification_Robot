:- dynamic world/1.

% ---------------------------------
% ACTION DEFINITIONS
% ---------------------------------
action(poweron).
action(poweroff).
action(scanarea).
action(moveforward).
action(turnleft).
action(turnright).
action(pickobject).
action(releaseobject).
action(checkbattery).
action(stop).

% ---------------------------------
% PRECONDITIONS
% ---------------------------------

% Power rules
precondition(poweron, powered_off).
precondition(poweroff, powered_on).

% Must be powered on for all robot tasks
precondition(scanarea, powered_on).
precondition(checkbattery, powered_on).

% Movement/actions require scanning first
precondition(moveforward, powered_on).
precondition(moveforward, scanned).

precondition(turnleft, powered_on).
precondition(turnleft, scanned).

precondition(turnright, powered_on).
precondition(turnright, scanned).

% Object rules
precondition(pickobject, powered_on).
precondition(pickobject, scanned).
precondition(pickobject, object_detected).

% You can only release if holding object
precondition(releaseobject, powered_on).
precondition(releaseobject, holding_object).

precondition(stop, powered_on).


% ---------------------------------
% INITIAL WORLD STATE
% ---------------------------------
world(powered_off).
world(battery_full).
world(object_detected).


% ---------------------------------
% STATE TRANSITIONS
% These modify world depending on executed action
% ---------------------------------

apply_action(poweron) :-
    retractall(world(powered_off)),
    assertz(world(powered_on)).

apply_action(poweroff) :-
    retractall(world(powered_on)),
    assertz(world(powered_off)).

apply_action(scanarea) :-
    assertz(world(scanned)).

apply_action(moveforward) :-
    retractall(world(battery_full)),
    assertz(world(battery_low)).

apply_action(pickobject) :-
    assertz(world(holding_object)).

apply_action(releaseobject) :-
    retractall(world(holding_object)).

apply_action(_) :- true. % default: no state change


% ---------------------------------
% VALIDATION ENTRY POINT
% validate(Action, Result)
% Also applies changes if action is valid
% ---------------------------------

validate(Action, "invalid_action") :-
    \+ action(Action), !.

validate(Action, "precondition_failed") :-
    precondition(Action, Cond),
    \+ world(Cond), !.

validate(Action, "valid") :-
    action(Action),
    forall(precondition(Action, Cond), world(Cond)), 
    apply_action(Action), !.
