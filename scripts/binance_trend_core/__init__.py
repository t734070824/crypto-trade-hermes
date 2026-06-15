"""Core realtime trading interfaces for Binance USDS-M trend system.

v1.4 only defines stable boundaries and lightweight wrappers. It does not
submit signed Binance orders; broker-specific behavior must stay isolated in
BrokerAdapter implementations.
"""

from .brokers import BrokerAdapter, RejectingBrokerAdapter
from .execution import ExecutionEngine, ExecutionPlan, OrderInstruction, PaperIntentExecutionEngine
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
]
