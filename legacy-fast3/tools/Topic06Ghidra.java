// Topic 06: dump the function that contains the patch site (RVA 0x777C8)
// from the ORIGINAL 7za.exe, together with the Ghidra version, file hash,
// callers and decompiler output. Intended for analyzeHeadless -postScript.
//
//   analyzeHeadless <proj_dir> <proj_name> -import 7za.exe -overwrite ^
//       -scriptPath tools -postScript Topic06Ghidra.java <output.txt>
//
//@category VNUK.Topic06
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.framework.Application;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.database.mem.AddressSourceInfo;
import ghidra.program.model.symbol.Reference;

public class Topic06Ghidra extends GhidraScript {
    private static final long PATCH_RVA = 0x777C8L;
    private static final int PATCH_LEN = 24;
    private static final long HANDLER_RVA = 0x783E9L;

    private StringBuilder out = new StringBuilder();

    private void line(String text) {
        out.append(text).append(System.lineSeparator());
    }

    private String hex(byte[] bytes) {
        StringBuilder sb = new StringBuilder();
        for (byte b : bytes) {
            sb.append(String.format("%02X ", b & 0xFF));
        }
        return sb.toString().trim();
    }

    private long rva(Address a) {
        return a.getOffset() - currentProgram.getImageBase().getOffset();
    }

    private void dumpInstruction(Instruction ins, Address patchStart, Address patchEnd) throws Exception {
        Address a = ins.getAddress();
        boolean inPatch = a.compareTo(patchStart) >= 0 && a.compareTo(patchEnd) < 0;
        AddressSourceInfo src = currentProgram.getMemory().getAddressSourceInfo(a);
        long fileOffset = src == null ? -1 : src.getFileOffset();
        line(String.format("%s %s  RVA=%05X FILE=%05X  %-24s %s",
            inPatch ? ">>" : "  ", a, rva(a), fileOffset, hex(ins.getBytes()), ins.toString()));
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        line("Tool: Ghidra " + Application.getApplicationVersion() + " "
            + Application.getApplicationReleaseName() + " (build "
            + Application.getBuildDate() + "), analyzeHeadless + Topic06Ghidra.java");
        line("Java: " + System.getProperty("java.vendor") + " " + System.getProperty("java.version"));
        line("Program: " + currentProgram.getName());
        line("Program SHA-256: " + currentProgram.getExecutableSHA256());
        line("Language: " + currentProgram.getLanguageID() + " / " + currentProgram.getCompilerSpec().getCompilerSpecID());
        line("Image base: " + currentProgram.getImageBase());

        Address patch = currentProgram.getImageBase().add(PATCH_RVA);
        Address patchEnd = patch.add(PATCH_LEN);
        AddressSourceInfo psrc = currentProgram.getMemory().getAddressSourceInfo(patch);
        line(String.format("Patch site: VA=%s RVA=%05X FILE=%05X length=%d bytes",
            patch, PATCH_RVA, psrc.getFileOffset(), PATCH_LEN));
        byte[] original = getBytes(patch, PATCH_LEN);
        line("Original bytes at patch site: " + hex(original));
        line("");

        Function f = getFunctionContaining(patch);
        if (f == null) {
            line("No function contained the patch site after auto-analysis.");
        } else {
            line(String.format("Function containing patch: %s entry=%s RVA=%05X body=%s-%s size=%d",
                f.getName(), f.getEntryPoint(), rva(f.getEntryPoint()),
                f.getBody().getMinAddress(), f.getBody().getMaxAddress(), f.getBody().getNumAddresses()));
            line("Signature: " + f.getSignature().getPrototypeString());
            line("");
            line("=== Disassembly of " + f.getName() + " (>> marks the 24-byte patch window) ===");
            InstructionIterator it = currentProgram.getListing().getInstructions(f.getBody(), true);
            while (it.hasNext()) {
                dumpInstruction(it.next(), patch, patchEnd);
            }
            line("");
            line("=== Callers of " + f.getName() + " ===");
            for (Reference ref : getReferencesTo(f.getEntryPoint())) {
                Address from = ref.getFromAddress();
                Function caller = getFunctionContaining(from);
                line(String.format("%s %s from %s (RVA=%05X) in %s", ref.getReferenceType(),
                    f.getEntryPoint(), from, rva(from),
                    caller == null ? "<no function>" : caller.getName() + "@" + caller.getEntryPoint()));
                Instruction ins = getInstructionAt(from);
                for (int i = 0; i < 8 && ins != null && ins.getPrevious() != null; i++) {
                    ins = ins.getPrevious();
                }
                for (int i = 0; i < 11 && ins != null; i++, ins = ins.getNext()) {
                    dumpInstruction(ins, from, from.add(1));
                }
                line("");
            }

            line("=== Decompiler output for " + f.getName() + " ===");
            DecompInterface dec = new DecompInterface();
            dec.openProgram(currentProgram);
            DecompileResults res = dec.decompileFunction(f, 120, monitor);
            if (res != null && res.decompileCompleted()) {
                line(res.getDecompiledFunction().getC());
            } else {
                line("Decompilation failed: " + (res == null ? "null" : res.getErrorMessage()));
            }
            dec.dispose();
        }

        Address handler = currentProgram.getImageBase().add(HANDLER_RVA);
        Function hf = getFunctionContaining(handler);
        line("=== x64dbg handler breakpoint RVA 783E9 ===");
        line("Function: " + (hf == null ? "<none>" : hf.getName() + " entry=" + hf.getEntryPoint()));
        Instruction ins = getInstructionAt(handler);
        for (int i = 0; i < 4 && ins != null && ins.getPrevious() != null; i++) {
            ins = ins.getPrevious();
        }
        for (int i = 0; i < 18 && ins != null; i++, ins = ins.getNext()) {
            dumpInstruction(ins, handler, handler.add(1));
        }

        String text = out.toString();
        if (args.length > 0) {
            Files.writeString(Path.of(args[0]), text, StandardCharsets.UTF_8);
            println("Topic06Ghidra wrote " + args[0]);
        } else {
            println(text);
        }
    }
}
