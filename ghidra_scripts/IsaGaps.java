// Find every place the disassembler stopped: an instruction with fall-through
// whose next address is not an instruction. Histogram the undecoded encoding
// there, so the failing opcode family is a measurement, not a guess.
//@category ISA
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSetView;
import ghidra.program.model.listing.*;
import ghidra.program.model.mem.MemoryBlock;
import java.util.*;

public class IsaGaps extends GhidraScript {
    @Override
    public void run() throws Exception {
        Listing lst = currentProgram.getListing();
        Map<String, Integer> hist = new HashMap<>();
        Map<String, List<String>> sites = new HashMap<>();
        int stops = 0, inFunc = 0;
        Set<String> funcs = new TreeSet<>();

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
            // a defined data item is a deliberate call, not a decode failure
            Data d = lst.getDefinedDataAt(nxt);
            if (d != null) continue;
            stops++;
            int w0, w1;
            try {
                w0 = currentProgram.getMemory().getShort(nxt) & 0xFFFF;
                w1 = currentProgram.getMemory().getShort(nxt.add(2)) & 0xFFFF;
            } catch (Exception e) { continue; }
            String key = String.format("%04x %04x", w0, w1);
            String kk = (w0 >= 0xC000) ? key : String.format("%04x ....", w0);
            hist.merge(kk, 1, Integer::sum);
            sites.computeIfAbsent(kk, k -> new ArrayList<>()).add(nxt.toString());
            Function f = lst.getFunctionContaining(ins.getAddress());
            if (f != null) { inFunc++; funcs.add(f.getName() + " @" + f.getEntryPoint()); }
            }
        }
        println("fallthrough_stops=" + stops + " inside_a_function=" + inFunc
                + " distinct_functions_truncated=" + funcs.size());
        List<String> keys = new ArrayList<>(hist.keySet());
        keys.sort((a, b) -> hist.get(b) - hist.get(a));
        StringBuilder sb = new StringBuilder("--- undecoded encodings at stop points ---\n");
        for (String k : keys) {
            List<String> s = sites.get(k);
            sb.append(String.format("%5d  %s   e.g. %s\n", hist.get(k), k,
                    String.join(",", s.subList(0, Math.min(3, s.size())))));
        }
        println(sb.toString());
        StringBuilder fb = new StringBuilder("--- truncated functions ---\n");
        for (String f : funcs) fb.append(f).append("\n");
        println(fb.toString());
    }
}
