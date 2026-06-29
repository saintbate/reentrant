"""Identify ISR root functions: IRQHandlers + HAL weak callbacks."""
from __future__ import annotations

import re

# STM32 IRQ handler suffix pattern — matches stm32xx_it.c naming
_IRQ_HANDLER_RE = re.compile(r"^[A-Za-z0-9_]+_IRQHandler$")

# HAL weak callbacks the user overrides — these run inside interrupt context
# even though they don't end in _IRQHandler.
_HAL_CALLBACKS: frozenset[str] = frozenset({
    # GPIO/EXTI
    "HAL_GPIO_EXTI_Callback",
    "HAL_GPIO_EXTI_Rising_Callback",
    "HAL_GPIO_EXTI_Falling_Callback",
    # Timers
    "HAL_TIM_PeriodElapsedCallback",
    "HAL_TIM_PeriodElapsedHalfCpltCallback",
    "HAL_TIM_OC_DelayElapsedCallback",
    "HAL_TIM_IC_CaptureCallback",
    "HAL_TIM_IC_CaptureHalfCpltCallback",
    "HAL_TIM_PWM_PulseFinishedCallback",
    "HAL_TIM_PWM_PulseFinishedHalfCpltCallback",
    "HAL_TIM_TriggerCallback",
    "HAL_TIM_TriggerHalfCpltCallback",
    "HAL_TIM_ErrorCallback",
    # UART
    "HAL_UART_TxCpltCallback",
    "HAL_UART_TxHalfCpltCallback",
    "HAL_UART_RxCpltCallback",
    "HAL_UART_RxHalfCpltCallback",
    "HAL_UART_ErrorCallback",
    "HAL_UART_AbortCpltCallback",
    "HAL_UART_AbortTransmitCpltCallback",
    "HAL_UART_AbortReceiveCpltCallback",
    "HAL_UARTEx_RxEventCallback",
    # SPI
    "HAL_SPI_TxCpltCallback",
    "HAL_SPI_RxCpltCallback",
    "HAL_SPI_TxRxCpltCallback",
    "HAL_SPI_ErrorCallback",
    # I2C
    "HAL_I2C_MasterTxCpltCallback",
    "HAL_I2C_MasterRxCpltCallback",
    "HAL_I2C_SlaveTxCpltCallback",
    "HAL_I2C_SlaveRxCpltCallback",
    "HAL_I2C_MemTxCpltCallback",
    "HAL_I2C_MemRxCpltCallback",
    "HAL_I2C_ErrorCallback",
    # ADC
    "HAL_ADC_ConvCpltCallback",
    "HAL_ADC_ConvHalfCpltCallback",
    "HAL_ADC_ErrorCallback",
    # DMA
    "HAL_DMA_XferCpltCallback",
    "HAL_DMA_XferHalfCpltCallback",
    "HAL_DMA_XferErrorCallback",
    # CAN / FDCAN
    "HAL_CAN_RxFifo0MsgPendingCallback",
    "HAL_CAN_RxFifo1MsgPendingCallback",
    "HAL_CAN_TxMailbox0CompleteCallback",
    "HAL_CAN_TxMailbox1CompleteCallback",
    "HAL_CAN_TxMailbox2CompleteCallback",
    "HAL_FDCAN_RxFifo0Callback",
    "HAL_FDCAN_RxFifo1Callback",
    "HAL_FDCAN_TxBufferCompleteCallback",
    # RTC
    "HAL_RTC_AlarmAEventCallback",
    "HAL_RTCEx_AlarmBEventCallback",
    "HAL_RTCEx_WakeUpTimerEventCallback",
    # USB
    "HAL_PCD_SetupStageCallback",
    "HAL_PCD_DataOutStageCallback",
    "HAL_PCD_DataInStageCallback",
    "HAL_PCD_SOFCallback",
    "HAL_PCD_ResetCallback",
    "HAL_PCD_SuspendCallback",
    "HAL_PCD_ResumeCallback",
    "HAL_PCD_ConnectCallback",
    "HAL_PCD_DisconnectCallback",
    # SAI
    "HAL_SAI_TxCpltCallback",
    "HAL_SAI_TxHalfCpltCallback",
    "HAL_SAI_RxCpltCallback",
    "HAL_SAI_RxHalfCpltCallback",
    "HAL_SAI_ErrorCallback",
    # Systick (runs as interrupt)
    "HAL_SYSTICK_Callback",
    "SysTick_Handler",
    # NMI / fault handlers
    "NMI_Handler",
    "HardFault_Handler",
    "MemManage_Handler",
    "BusFault_Handler",
    "UsageFault_Handler",
    "SVC_Handler",
    "DebugMon_Handler",
    "PendSV_Handler",
})


def find_isr_roots(function_names: set[str]) -> set[str]:
    """Return subset of function_names that are ISR roots."""
    roots: set[str] = set()
    for name in function_names:
        if _IRQ_HANDLER_RE.match(name) or name in _HAL_CALLBACKS:
            roots.add(name)
    return roots
