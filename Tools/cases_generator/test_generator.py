# Sorry for using pytest, these tests are mostly just for me.
# Use pytest -vv for best results.

import tempfile

import generate_cases
from parser import StackEffect


def test_effect_sizes():
    input_effects = [
        x := StackEffect("x", "", "", ""),
        y := StackEffect("y", "", "", "oparg"),
        z := StackEffect("z", "", "", "oparg*2"),
    ]
    output_effects = [
        StackEffect("a", "", "", ""),
        StackEffect("b", "", "", "oparg*4"),
        StackEffect("c", "", "", ""),
    ]
    other_effects = [
        StackEffect("p", "", "", "oparg<<1"),
        StackEffect("q", "", "", ""),
        StackEffect("r", "", "", ""),
    ]
    assert generate_cases.effect_size(x) == (1, "")
    assert generate_cases.effect_size(y) == (0, "oparg")
    assert generate_cases.effect_size(z) == (0, "oparg*2")

    assert generate_cases.list_effect_size(input_effects) == (1, "oparg + oparg*2")
    assert generate_cases.list_effect_size(output_effects) == (2, "oparg*4")
    assert generate_cases.list_effect_size(other_effects) == (2, "(oparg<<1)")

    assert generate_cases.string_effect_size(generate_cases.list_effect_size(input_effects)) == "1 + oparg + oparg*2"
    assert generate_cases.string_effect_size(generate_cases.list_effect_size(output_effects)) == "2 + oparg*4"
    assert generate_cases.string_effect_size(generate_cases.list_effect_size(other_effects)) == "2 + (oparg<<1)"


def run_cases_test(input: str, expected: str):
    temp_input = tempfile.NamedTemporaryFile("w+")
    temp_input.write(generate_cases.BEGIN_MARKER)
    temp_input.write(input)
    temp_input.write(generate_cases.END_MARKER)
    temp_input.flush()
    temp_output = tempfile.NamedTemporaryFile("w+")
    temp_metadata = tempfile.NamedTemporaryFile("w+")
    a = generate_cases.Analyzer([temp_input.name], temp_output.name, temp_metadata.name)
    a.parse()
    a.analyze()
    if a.errors:
        raise RuntimeError(f"Found {a.errors} errors")
    a.write_instructions()
    temp_output.seek(0)
    lines = temp_output.readlines()
    while lines and lines[0].startswith("// "):
        lines.pop(0)
    actual = "".join(lines)
    # if actual.rstrip() != expected.rstrip():
    #     print("Actual:")
    #     print(actual)
    #     print("Expected:")
    #     print(expected)
    #     print("End")
    assert actual.rstrip() == expected.rstrip()

def test_inst_no_args():
    input = """
        inst(OP, (--)) {
            spam();
        }
    """
    output = """
        TARGET(OP) {
            spam();
            DISPATCH();
        }
    """
    run_cases_test(input, output)

def test_inst_one_pop():
    input = """
        inst(OP, (value --)) {
            spam();
        }
    """
    output = """
        TARGET(OP) {
            PyObject *value = stack_pointer[-1];
            spam();
            STACK_SHRINK(1);
            DISPATCH();
        }
    """
    run_cases_test(input, output)

def test_inst_one_push():
    input = """
        inst(OP, (-- res)) {
            spam();
        }
    """
    output = """
        TARGET(OP) {
            PyObject *res;
            spam();
            STACK_GROW(1);
            stack_pointer[-1] = res;
            DISPATCH();
        }
    """
    run_cases_test(input, output)

def test_inst_one_push_one_pop():
    input = """
        inst(OP, (value -- res)) {
            spam();
        }
    """
    output = """
        TARGET(OP) {
            PyObject *value = stack_pointer[-1];
            PyObject *res;
            spam();
            stack_pointer[-1] = res;
            DISPATCH();
        }
    """
    run_cases_test(input, output)

def test_binary_op():
    input = """
        inst(OP, (left, right -- res)) {
            spam();
        }
    """
    output = """
        TARGET(OP) {
            PyObject *right = stack_pointer[-1];
            PyObject *left = stack_pointer[-2];
            PyObject *res;
            spam();
            STACK_SHRINK(1);
            stack_pointer[-1] = res;
            DISPATCH();
        }
    """
    run_cases_test(input, output)

def test_overlap():
    input = """
        inst(OP, (left, right -- left, result)) {
            spam();
        }
    """
    output = """
        TARGET(OP) {
            PyObject *right = stack_pointer[-1];
            PyObject *left = stack_pointer[-2];
            PyObject *result;
            spam();
            stack_pointer[-1] = result;
            DISPATCH();
        }
    """
    run_cases_test(input, output)

def test_predictions_and_eval_breaker():
    input = """
        inst(OP1, (--)) {
        }
        inst(OP3, (arg -- res)) {
            DEOPT_IF(xxx, OP1);
            CHECK_EVAL_BREAKER();
        }
    """
    output = """
        TARGET(OP1) {
            PREDICTED(OP1);
            DISPATCH();
        }

        TARGET(OP3) {
            PyObject *arg = stack_pointer[-1];
            PyObject *res;
            DEOPT_IF(xxx, OP1);
            stack_pointer[-1] = res;
            CHECK_EVAL_BREAKER();
            DISPATCH();
        }
    """
    run_cases_test(input, output)

def test_error_if_plain():
    input = """
        inst(OP, (--)) {
            ERROR_IF(cond, label);
        }
    """
    output = """
        TARGET(OP) {
            if (cond) goto label;
            DISPATCH();
        }
    """
    run_cases_test(input, output)

def test_error_if_plain_with_comment():
    input = """
        inst(OP, (--)) {
            ERROR_IF(cond, label);  // Comment is ok
        }
    """
    output = """
        TARGET(OP) {
            if (cond) goto label;
            DISPATCH();
        }
    """
    run_cases_test(input, output)

def test_error_if_pop():
    input = """
        inst(OP, (left, right -- res)) {
            ERROR_IF(cond, label);
        }
    """
    output = """
        TARGET(OP) {
            PyObject *right = stack_pointer[-1];
            PyObject *left = stack_pointer[-2];
            PyObject *res;
            if (cond) goto pop_2_label;
            STACK_SHRINK(1);
            stack_pointer[-1] = res;
            DISPATCH();
        }
    """
    run_cases_test(input, output)

def test_cache_effect():
    input = """
        inst(OP, (counter/1, extra/2, value --)) {
        }
    """
    output = """
        TARGET(OP) {
            PyObject *value = stack_pointer[-1];
            uint16_t counter = read_u16(&next_instr[0].cache);
            uint32_t extra = read_u32(&next_instr[1].cache);
            STACK_SHRINK(1);
            next_instr += 3;
            DISPATCH();
        }
    """
    run_cases_test(input, output)

def test_suppress_dispatch():
    input = """
        inst(OP, (--)) {
            goto somewhere;
        }
    """
    output = """
        TARGET(OP) {
            goto somewhere;
        }
    """
    run_cases_test(input, output)

def test_macro_instruction():
    input = """
        inst(OP1, (counter/1, left, right -- left, right)) {
            op1(left, right);
        }
        op(OP2, (extra/2, arg2, left, right -- res)) {
            res = op2(arg2, left, right);
        }
        macro(OP) = OP1 + cache/2 + OP2;
        inst(OP3, (unused/5, arg2, left, right -- res)) {
            res = op3(arg2, left, right);
        }
        family(op, INLINE_CACHE_ENTRIES_OP) = { OP, OP3 };
    """
    output = """
        TARGET(OP1) {
            PyObject *right = stack_pointer[-1];
            PyObject *left = stack_pointer[-2];
            uint16_t counter = read_u16(&next_instr[0].cache);
            op1(left, right);
            next_instr += 1;
            DISPATCH();
        }

        TARGET(OP) {
            PyObject *_tmp_1 = stack_pointer[-1];
            PyObject *_tmp_2 = stack_pointer[-2];
            PyObject *_tmp_3 = stack_pointer[-3];
            {
                PyObject *right = _tmp_1;
                PyObject *left = _tmp_2;
                uint16_t counter = read_u16(&next_instr[0].cache);
                op1(left, right);
                _tmp_2 = left;
                _tmp_1 = right;
            }
            {
                PyObject *right = _tmp_1;
                PyObject *left = _tmp_2;
                PyObject *arg2 = _tmp_3;
                PyObject *res;
                uint32_t extra = read_u32(&next_instr[3].cache);
                res = op2(arg2, left, right);
                _tmp_3 = res;
            }
            next_instr += 5;
            static_assert(INLINE_CACHE_ENTRIES_OP == 5, "incorrect cache size");
            STACK_SHRINK(2);
            stack_pointer[-1] = _tmp_3;
            DISPATCH();
        }

        TARGET(OP3) {
            PyObject *right = stack_pointer[-1];
            PyObject *left = stack_pointer[-2];
            PyObject *arg2 = stack_pointer[-3];
            PyObject *res;
            res = op3(arg2, left, right);
            STACK_SHRINK(2);
            stack_pointer[-1] = res;
            next_instr += 5;
            DISPATCH();
        }
    """
    run_cases_test(input, output)

def test_array_input():
    input = """
        inst(OP, (below, values[oparg*2], above --)) {
            spam();
        }
    """
    output = """
        TARGET(OP) {
            PyObject *above = stack_pointer[-1];
            PyObject **values = (stack_pointer - (1 + oparg*2));
            PyObject *below = stack_pointer[-(2 + oparg*2)];
            spam();
            STACK_SHRINK(oparg*2);
            STACK_SHRINK(2);
            DISPATCH();
        }
    """
    run_cases_test(input, output)

def test_array_output():
    input = """
        inst(OP, (unused, unused -- below, values[oparg*3], above)) {
            spam(values, oparg);
        }
    """
    output = """
        TARGET(OP) {
            PyObject *below;
            PyObject **values = stack_pointer - (2) + 1;
            PyObject *above;
            spam(values, oparg);
            STACK_GROW(oparg*3);
            stack_pointer[-1] = above;
            stack_pointer[-(2 + oparg*3)] = below;
            DISPATCH();
        }
    """
    run_cases_test(input, output)

def test_array_input_output():
    input = """
        inst(OP, (values[oparg] -- values[oparg], above)) {
            spam(values, oparg);
        }
    """
    output = """
        TARGET(OP) {
            PyObject **values = (stack_pointer - oparg);
            PyObject *above;
            spam(values, oparg);
            STACK_GROW(1);
            stack_pointer[-1] = above;
            DISPATCH();
        }
    """
    run_cases_test(input, output)

def test_array_error_if():
    input = """
        inst(OP, (extra, values[oparg] --)) {
            ERROR_IF(oparg == 0, somewhere);
        }
    """
    output = """
        TARGET(OP) {
            PyObject **values = (stack_pointer - oparg);
            PyObject *extra = stack_pointer[-(1 + oparg)];
            if (oparg == 0) { STACK_SHRINK(oparg); goto pop_1_somewhere; }
            STACK_SHRINK(oparg);
            STACK_SHRINK(1);
            DISPATCH();
        }
    """
    run_cases_test(input, output)

def test_cond_effect():
    input = """
        inst(OP, (aa, input if ((oparg & 1) == 1), cc -- xx, output if (oparg & 2), zz)) {
            output = spam(oparg, input);
        }
    """
    output = """
        TARGET(OP) {
            PyObject *cc = stack_pointer[-1];
            PyObject *input = ((oparg & 1) == 1) ? stack_pointer[-(1 + (((oparg & 1) == 1) ? 1 : 0))] : NULL;
            PyObject *aa = stack_pointer[-(2 + (((oparg & 1) == 1) ? 1 : 0))];
            PyObject *xx;
            PyObject *output = NULL;
            PyObject *zz;
            output = spam(oparg, input);
            STACK_SHRINK((((oparg & 1) == 1) ? 1 : 0));
            STACK_GROW(((oparg & 2) ? 1 : 0));
            stack_pointer[-1] = zz;
            if (oparg & 2) { stack_pointer[-(1 + ((oparg & 2) ? 1 : 0))] = output; }
            stack_pointer[-(2 + ((oparg & 2) ? 1 : 0))] = xx;
            DISPATCH();
        }
    """
    run_cases_test(input, output)
