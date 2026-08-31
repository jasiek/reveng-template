// Transitive callee closure of a function, with the things that would stop an
// emulator: MMIO references, indirect calls, and calls that leave the closure.
// Args: <entryHex> ...
//@category Emulation
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.*;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.*;
import java.util.*;

public class ClosureAudit extends GhidraScript {
    @Override
    public void run() throws Exception {
        Set<Function> seen = new LinkedHashSet<>();
        Deque<Function> work = new ArrayDeque<>();
        for (String tok : String.join(" ", getScriptArgs())
                                .replace("[","").replace("]","").replace(",", " ").trim().split("\\s+")) {
            if (tok.isEmpty()) continue;
            Function f = getFunctionAt(toAddr(Long.parseLong(tok, 16)));
            if (f != null) { seen.add(f); work.add(f); }
        }
        while (!work.isEmpty()) {
            Function f = work.poll();
            for (Function c : f.getCalledFunctions(monitor))
                if (seen.add(c)) work.add(c);
        }
        println("closure_size=" + seen.size());
        Map<String, Integer> mmio = new TreeMap<>();
        List<String> indirect = new ArrayList<>();
        long bytes = 0;
        for (Function f : seen) {
            bytes += f.getBody().getNumAddresses();
            InstructionIterator it = currentProgram.getListing().getInstructions(f.getBody(), true);
            while (it.hasNext()) {
                Instruction ins = it.next();
                for (Reference r : ins.getReferencesFrom()) {
                    Address t = r.getToAddress();
                    MemoryBlock mb = currentProgram.getMemory().getBlock(t);
                    if (mb != null && mb.getName().startsWith("MMIO"))
                        mmio.merge(mb.getName() + " " + t, 1, Integer::sum);
                }
                FlowType ft = ins.getFlowType();
                if (ft.isCall() && ins.getFlows().length == 0)
                    indirect.add(ins.getAddress() + "  " + ins);
            }
        }
        println("closure_bytes=" + bytes);
        println("--- MMIO touched (" + mmio.size() + ") ---");
        for (Map.Entry<String, Integer> e : mmio.entrySet()) println("  " + e.getKey() + " x" + e.getValue());
        println("--- indirect calls (" + indirect.size() + ") ---");
        for (String s : indirect) println("  " + s);
        println("--- functions ---");
        for (Function f : seen) println("  " + f.getEntryPoint() + " " + f.getName()
                                        + " (" + f.getBody().getNumAddresses() + ")");
    }
}
