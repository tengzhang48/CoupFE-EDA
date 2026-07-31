# Phase-2 exporter: OpenDB -> solver-neutral case files.
#
# Reads a placed+PDN OpenDB and writes:
#   instances.csv  - per-instance eda_id, master, placement bbox (um), area
#   manifest.json  - die/core bbox, dbu, instance count, units
#
# Runs in the EDA conda env (OpenROAD); the CoupFE solver (separate venv) consumes
# the files. Decoupled by the case format — exactly the plan's data contract.
#
# Usage (env vars):
#   TECH_LEF, SC_LEF, IN_ODB, OUT_DIR
#   openroad -exit eda_multiphysics/openroad/export_case.tcl

read_lef $::env(TECH_LEF)
read_lef $::env(SC_LEF)
read_db  $::env(IN_ODB)

set block [ord::get_db_block]
set dbu   [$block getDbUnitsPerMicron]
set out   $::env(OUT_DIR)
file mkdir $out

# --- instances ---
set fp [open $out/instances.csv w]
puts $fp "eda_id,master,x_um,y_um,w_um,h_um,area_um2"
set n 0
foreach inst [$block getInsts] {
    set bb [$inst getBBox]
    set x0 [expr {[$bb xMin] / double($dbu)}]
    set y0 [expr {[$bb yMin] / double($dbu)}]
    set w  [expr {([$bb xMax] - [$bb xMin]) / double($dbu)}]
    set h  [expr {([$bb yMax] - [$bb yMin]) / double($dbu)}]
    set a  [expr {$w * $h}]
    puts $fp "[$inst getName],[[$inst getMaster] getName],$x0,$y0,$w,$h,$a"
    incr n
}
close $fp

# --- manifest ---
set die  [$block getDieArea]
set core [$block getCoreArea]
set mf [open $out/manifest.json w]
puts $mf "{"
puts $mf "  \"design\": \"[$block getName]\","
puts $mf "  \"dbu_per_micron\": $dbu,"
puts $mf "  \"units\": \"micron\","
puts $mf "  \"n_instances\": $n,"
puts $mf "  \"die_um\":  \[[expr {[$die xMin]/double($dbu)}], [expr {[$die yMin]/double($dbu)}], [expr {[$die xMax]/double($dbu)}], [expr {[$die yMax]/double($dbu)}]\],"
puts $mf "  \"core_um\": \[[expr {[$core xMin]/double($dbu)}], [expr {[$core yMin]/double($dbu)}], [expr {[$core xMax]/double($dbu)}], [expr {[$core yMax]/double($dbu)}]\]"
puts $mf "}"
close $mf

puts "EXPORT_OK: $n instances -> $out"
