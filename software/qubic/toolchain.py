import distproc.compiler as cm
import distproc.assembler as am
import qubic.rfsoc.hwconfig as hw
import qubitconfig.qchip as qc
import json
import os

def run_compile_stage(program, fpga_config, qchip):
    """
    Wrapper around distributed processor compiler stage. Will add more
    options/functionality as QubiC evolves and more platforms are included

    Parameters
    ----------

    Returns
    -------
	CompiledProgram
	    Object containing compiled
    """

    if isinstance(program[0], dict):
        compiler = cm.Compiler(program, 'by_qubit', fpga_config, qchip)
        return compiler.compile()
    elif isinstance(program[0], list):
        compiled_progs = []
        for circuit in program:
            compiler = cm.Compiler(circuit, 'by_qubit', fpga_config, qchip)
            compiled_progs.append(compiler.compile())
        return compiled_progs
    else:
        raise TypeError

def run_assemble_stage(compiled_program, channel_configs, target_platform='rfsoc'):
    """
    Wrapper around distributed processor assembler stage. Will add more
    options/functionality as QubiC evolves and more platforms are included
    """
    if target_platform != 'rfsoc':
        raise Exception('rfsoc is currently the only supported platform!')

    if isinstance(compiled_program, list):
        raw_asm_progs = []
        for prog in compiled_program:
            asm = am.GlobalAssembler(prog, channel_configs, hw.RFSoCElementCfg)
            raw_asm_progs.append(asm.get_assembled_program())
        return raw_asm_progs

    else:
        asm = am.GlobalAssembler(compiled_program, channel_configs, hw.RFSoCElementCfg)
        return asm.get_assembled_program()

def build_fromdict(build_dict):
    """
    Build a QubiC program from a build dict specifying paths to source, compiled,
    and assembled programs, as well as relevant config infos. Primary use is building
    and running programs from yml configurations.
    """
    assemble_dict = build_dict['assemble_stage']
    if 'compile_stage' in build_dict.keys():
        compile_dict = build_dict['compile_stage']
        with open(compile_dict['source']) as f:
            prog_dict = json.load(f)
        with open(compile_dict['fpga_config']) as f:
            fpga_config = hw.FPGAConfig(**json.load(f))
        qchip = qc.QChip(compile_dict['qchip'])
        compiled_prog = run_compile_stage(prog_dict, fpga_config, qchip)
    else:
        compiled_prog = cm.load_compiled_program(assemble_dict['source'])

    channel_configs = hw.load_channel_configs(assemble_dict['channel_configs'])
    return run_assemble_stage(compiled_prog, channel_configs)

