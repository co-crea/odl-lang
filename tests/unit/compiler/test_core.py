import pytest
from unittest.mock import MagicMock, call, patch

from odl.compiler.core import compile_odl
from odl.compiler.exceptions import OdlCompilationError
from odl.types import IrComponent, OpCode

class TestCore:
    """
    BP-L1-01-ODL-COMPILER: Compiler Facade & Orchestration
    のUnit Test (Mock Based) を実装する。
    """

    @pytest.fixture
    def mocks(self):
        """パイプラインの各構成要素をMock化する"""
        with patch("odl.compiler.core.parser") as mock_parser, \
             patch("odl.compiler.core.expander") as mock_expander, \
             patch("odl.compiler.core.resolver") as mock_resolver, \
             patch("odl.compiler.core.assembler") as mock_assembler, \
             patch("odl.compiler.core.syntax") as mock_syntax, \
             patch("odl.compiler.core.wiring") as mock_wiring:
            
            yield {
                "parser": mock_parser,
                "expander": mock_expander,
                "resolver": mock_resolver,
                "assembler": mock_assembler,
                "syntax": mock_syntax,
                "wiring": mock_wiring,
            }

    def test_tc_compiler_001_interface_availability(self):
        """
        TC-COMPILER-001: Public Interface Availability
        compile_odl 関数が公開され、呼び出し可能であること。
        """
        assert callable(compile_odl)

    def test_tc_compiler_002_pipeline_execution_order(self, mocks):
        """
        TC-COMPILER-002: Full Pipeline Execution Order & Data Flow
        6つの工程が正しい順序で呼ばれ、データがリレーされていること。
        """
        # Arrange
        source_yaml = "opcode: serial"
        raw_dict = {"stage": "raw"}
        expanded_dict = {"stage": "expanded"}
        resolved_dict = {"stage": "resolved"}
        
        # 修正箇所: idフィールドを追加
        expected_ir = IrComponent(stack_path="test-root-id", opcode=OpCode.SERIAL)

        mocks["parser"].parse.return_value = raw_dict
        mocks["expander"].expand.return_value = expanded_dict
        mocks["resolver"].resolve.return_value = resolved_dict
        mocks["assembler"].assemble.return_value = expected_ir

        # Act
        result = compile_odl(source_yaml)

        # Assert
        assert result == expected_ir

        # 1. Parse
        mocks["parser"].parse.assert_called_once_with(source_yaml)
        
        # 2. Syntax Check (Must use Raw)
        mocks["syntax"].validate.assert_called_once_with(raw_dict)
        
        # 3. Expand (Must use Raw)
        mocks["expander"].expand.assert_called_once_with(raw_dict)
        
        # 4. Resolve (Must use Expanded)
        mocks["resolver"].resolve.assert_called_once_with(expanded_dict)
        
        # 5. Wiring Check (Must use Resolved)
        mocks["wiring"].validate.assert_called_once_with(resolved_dict)
        
        # 6. Assemble (Must use Resolved)
        mocks["assembler"].assemble.assert_called_once_with(resolved_dict)

    def test_tc_compiler_003_fail_fast_syntax_error(self, mocks):
        """
        TC-COMPILER-003: Fail-Fast Behavior (Syntax Error)
        Syntax Validatorでエラーが発生した場合、後続処理が実行されないこと。
        """
        # Arrange
        mocks["parser"].parse.return_value = {}
        mocks["syntax"].validate.side_effect = OdlCompilationError("Syntax Error")

        # Act & Assert
        with pytest.raises(OdlCompilationError, match="Syntax Error"):
            compile_odl("invalid_source")

        # Verify: 後続処理が呼ばれていないこと
        mocks["expander"].expand.assert_not_called()
        mocks["resolver"].resolve.assert_not_called()
        mocks["assembler"].assemble.assert_not_called()

    def test_tc_compiler_004_exception_wrapping(self, mocks):
        """
        TC-COMPILER-004: Exception Wrapping & Cause Preservation
        内部コンポーネントの予期せぬ例外がOdlCompilationErrorにラップされること。
        """
        # Arrange
        mocks["parser"].parse.return_value = {}
        # Expanderで想定外のシステムエラー（KeyError等）が発生
        mocks["expander"].expand.side_effect = KeyError("Internal Logic Error")

        # Act & Assert
        with pytest.raises(OdlCompilationError) as exc_info:
            compile_odl("source")
        
        # ラップされたメッセージと、原因(cause)の保持を確認
        assert "Internal compilation error" in str(exc_info.value)
        assert isinstance(exc_info.value.__cause__, KeyError)

    def test_tc_compiler_005_empty_input_guard(self, mocks):
        """
        TC-COMPILER-005: Empty Input Guard
        空文字やNoneが渡された場合、パイプラインを起動せずにエラーにすること。
        """
        # Act & Assert
        with pytest.raises(OdlCompilationError, match="Empty ODL source"):
            compile_odl("")
        
        with pytest.raises(OdlCompilationError, match="Empty ODL source"):
            # 型ヒント上はstrだが、実行時のNoneチェックも想定
            compile_odl(None) # type: ignore

        # Verify: Parserすら呼ばれていないこと
        mocks["parser"].parse.assert_not_called()