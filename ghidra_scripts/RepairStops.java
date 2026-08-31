// Repair every point where the disassembler stopped: retry the decode at the
// address, then fix up the containing function's body.
//
// Non-destructive by construction. It never removes the function, so names,
// signatures, parameter names and plate comments survive - which matters here
// because phase 2b committed signatures for 1284 functions and the naming
// campaign's plate comments are the audit trail. RepairRange.java's
// remove-clear-disassemble-recreate cycle throws all of that away.
//
// Iterates: repairing one stop can expose the next instruction wall behind it.
//@category Repair
import ghidra.app.cmd.function.CreateFunctionCmd;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.*;
import ghidra.program.model.mem.MemoryBlock;
import java.util.*;

public class RepairStops extends GhidraScript {

    private List<Address> findStops() {
        Listing lst = currentProgram.getListing();
        List<Address> stops = new ArrayList<>();
        InstructionIterator it = lst.getInstructions(true);
        while (it.hasNext()) {
            Instruction ins = it.next();
            List<Address> cand = new ArrayList<>();
            if (ins.hasFallthrough() && ins.getFallThrough() != null)
                cand.add(ins.getFallThrough());
            // a branch into bytes that were never decoded costs the decompiler
            // the same halt_baddata as a fall-through into them, and is invisible
            // to a fall-through-only scan
            for (Address fl : ins.getFlows()) cand.add(fl);
            for (Address nxt : cand) {
                MemoryBlock mb = currentProgram.getMemory().getBlock(nxt);
                if (mb == null || !mb.isExecute()) continue;
                if (lst.getInstructionAt(nxt) != null) continue;
                if (lst.getDefinedDataAt(nxt) != null) continue;
                stops.add(nxt);
            }
        }
        List<Address> uniq = new ArrayList<>(new LinkedHashSet<>(stops));
        return uniq;
    }

    @Override
    public void run() throws Exception {
        int maxPasses = 8;
        Map<String, long[]> touched = new TreeMap<>();  // name@entry -> {before, after}
        for (int pass = 1; pass <= maxPasses; pass++) {
            List<Address> stops = findStops();
            println("pass " + pass + ": " + stops.size() + " stop points");
            if (stops.isEmpty()) break;
            int fixed = 0, still = 0;
            for (Address a : stops) {
                Function f = nearestFunction(a);
                disassemble(a);
                if (currentProgram.getListing().getInstructionAt(a) == null) {
                    still++;
                    println("  STILL BAD @" + a + "  bytes=" + hexAt(a));
                    continue;
                }
                fixed++;
                if (f != null) {
                    String key = f.getName() + " @" + f.getEntryPoint();
                    long before = f.getBody().getNumAddresses();
                    CreateFunctionCmd.fixupFunctionBody(currentProgram, f, monitor);
                    long after = f.getBody().getNumAddresses();
                    long[] e = touched.get(key);
                    if (e == null) touched.put(key, new long[]{before, after});
                    else e[1] = after;
                }
            }
            println("  decoded " + fixed + ", still undecodable " + still);
            if (fixed == 0) break;
        }
        println("--- functions whose body was fixed up ---");
        for (Map.Entry<String, long[]> e : touched.entrySet())
            println(String.format("  %-56s %5d -> %5d bytes", e.getKey(), e.getValue()[0], e.getValue()[1]));
        println("remaining stop points: " + findStops().size());
    }

    // the function whose body ends closest above this address - for a branch
    // target that is the dispatcher/caller whose body should absorb it
    private Function nearestFunction(Address a) {
        Function best = null;
        for (Function f : currentProgram.getFunctionManager().getFunctions(true)) {
            if (f.getEntryPoint().compareTo(a) > 0) continue;
            if (best == null || f.getEntryPoint().compareTo(best.getEntryPoint()) > 0) best = f;
        }
        return best;
    }

    private String hexAt(Address a) {
        StringBuilder sb = new StringBuilder();
        try {
            for (int i = 0; i < 4; i++)
                sb.append(String.format("%02x", currentProgram.getMemory().getByte(a.add(i))));
        } catch (Exception e) { return "??"; }
        return sb.toString();
    }
}
