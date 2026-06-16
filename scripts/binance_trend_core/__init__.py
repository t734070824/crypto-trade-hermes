"""Core realtime trading interfaces for Binance USDS-M trend system.

v1.4 only defines stable boundaries and lightweight wrappers. It does not
submit signed Binance orders; broker-specific behavior must stay isolated in
BrokerAdapter implementations.
"""

from .brokers import BrokerAdapter, PaperBroker, RejectingBrokerAdapter
from .evolution import build_runtime_replay_dataset, compare_runtime_strategy_variants, load_runtime_records
from .execution import ExecutionEngine, ExecutionPlan, OrderInstruction, PaperIntentExecutionEngine
from .loop import TradingCycleConfig, run_trading_cycle
from .market_data import FunctionMarketData, MarketData
from .portfolio import PortfolioPosition, PortfolioState
from .risk import FunctionRiskManager, RiskManager
from .runtime import FunctionRuntimeRecorder, RuntimeRecorder
from .signals import FunctionSignalEngine, SignalEngine
from .strategy import TrendParticipationStrategy, Strategy
from .types import MarketDataRequest, StrategyIntent

__all__ = [
    "BrokerAdapter",
    "ExecutionEngine",
    "ExecutionPlan",
    "FunctionMarketData",
    "FunctionRiskManager",
    "FunctionRuntimeRecorder",
    "FunctionSignalEngine",
    "MarketData",
    "MarketDataRequest",
    "OrderInstruction",
    "PaperBroker",
    "PaperIntentExecutionEngine",
    "PortfolioPosition",
    "PortfolioState",
    "RejectingBrokerAdapter",
    "RiskManager",
    "RuntimeRecorder",
    "SignalEngine",
    "Strategy",
    "StrategyIntent",
    "TrendParticipationStrategy",
    "TradingCycleConfig",
    "build_runtime_replay_dataset",
    "compare_runtime_strategy_variants",
    "load_runtime_records",
    "run_trading_cycle",
]
