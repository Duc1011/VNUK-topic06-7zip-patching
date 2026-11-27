//@category VNUK.Topic06
import java.nio.file.Files;
import java.nio.file.Path;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.script.GhidraScript;
import ghidra.framework.Application;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;

public class Topic06Method extends GhidraScript {
    @Override
    public void run() throws Exception {
        Address base = currentProgram.getImageBase();
        Address patch = base.add(0x78339);
        Function handler = getFunctionContaining(patch);
        if (handler == null || !handler.getEntryPoint().equals(base.add(0x7829C))) {
            throw new IllegalStateException("Expected the method handler at RVA 7829C");
        }
        StringBuilder out = new StringBuilder();
        out.append(String.format("Ghidra %s %s%nProgram: %s%nSHA-256: %s%nImage base: %s%nHandler: %s at %s%n%n",
            Application.getApplicationVersion(), Application.getApplicationReleaseName(), currentProgram.getName(),
            currentProgram.getExecutableSHA256(), base, handler.getName(), handler.getEntryPoint()));
        for (Instruction ins = getInstructionAt(base.add(0x782E1));
                ins != null && ins.getAddress().compareTo(base.add(0x78368)) < 0; ins = ins.getNext()) {
            var address = ins.getAddress();
            long offset = currentProgram.getMemory().getAddressSourceInfo(address).getFileOffset();
            StringBuilder bytes = new StringBuilder();
            for (byte value : ins.getBytes()) {
                bytes.append(String.format("%02X ", value & 0xff));
            }
            out.append(String.format("%s  RVA=%05X FILE=%05X  %-24s %s%n", address,
                address.subtract(base), offset, bytes, ins));
        }
        out.append("\nStrings and incoming references\n");
        for (long rva : new long[] {0xFC7C0, 0xFD1E0, 0xFD580}) {
            Address string = base.add(rva);
            out.append(String.format("%s %s%n", string, getDataAt(string)));
            for (var ref : getReferencesTo(string)) {
                out.append(String.format("  %s %s%n", ref.getFromAddress(), ref.getReferenceType()));
            }
        }
        DecompInterface decompiler = new DecompInterface();
        try {
            decompiler.openProgram(currentProgram);
            var result = decompiler.decompileFunction(handler, 120, monitor);
            if (!result.decompileCompleted()) {
                throw new IllegalStateException(result.getErrorMessage());
            }
            out.append("\nDecompiled handler\n").append(result.getDecompiledFunction().getC());
        } finally {
            decompiler.dispose();
        }
        Files.writeString(Path.of(getScriptArgs()[0]), out.toString());
    }
}
