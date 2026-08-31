// Dump every decoded instruction as "addr len mnemonic bytes" to a file.
// Input for the differential disassembly audit (tools/isa_audit/).
//@category ISA
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import java.io.*;

public class DumpInsns extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] a = getScriptArgs();
        String out = (a.length > 0) ? a[0] : "/tmp/ghidra_insns.txt";
        PrintWriter pw = new PrintWriter(new BufferedWriter(new FileWriter(out)));
        int n = 0;
        InstructionIterator it = currentProgram.getListing().getInstructions(true);
        while (it.hasNext()) {
            Instruction ins = it.next();
            byte[] b = ins.getBytes();
            StringBuilder hb = new StringBuilder();
            for (byte x : b) hb.append(String.format("%02x", x));
            pw.printf("%s %d %s %s%n", ins.getAddress().toString(), ins.getLength(),
                      ins.getMnemonicString(), hb.toString());
            n++;
        }
        pw.close();
        println("wrote " + n + " instructions to " + out);
    }
}
