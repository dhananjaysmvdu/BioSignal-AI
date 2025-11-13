#!/usr/bin/env python3
"""
Adaptive Governance Controller v2 — Risk-Aware Feedback System

Auto-adjusts learning rate factors based on forecast risk metrics (FDI/CS).
Triggers alerts when prediction accuracy degrades or confidence becomes unstable.

Integration: Runs after predictive engine (00:30 UTC) and before nightly validation (02:00 UTC)
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Tuple


class AdaptiveControllerV2:
    """Risk-aware adaptive controller with FDI/CS-based feedback."""
    
    # Risk thresholds from predictive_engine/config.yml
    FDI_EXCELLENT = 5.0
    FDI_GOOD = 10.0
    FDI_WARNING = 15.0
    CS_STABLE = 3.0
    CS_UNSTABLE = 5.0
    
    # Learning rate adjustment factors
    LR_FACTOR_EXCELLENT = 1.2  # Boost learning when predictions are accurate
    LR_FACTOR_GOOD = 1.0       # Maintain baseline when acceptable
    LR_FACTOR_DRIFTING = 0.8   # Reduce learning when drifting
    LR_FACTOR_CRITICAL = 0.5   # Strong reduction when critical
    
    def __init__(self, workspace_root: Path):
        self.workspace = workspace_root
        self.forecast_risk_path = workspace_root / "reports" / "forecast_risk_assessment.json"
        self.predictive_metrics_path = workspace_root / "forecast" / "predictive_metrics_Q1_2026.json"
        self.output_path = workspace_root / "reports" / "adaptive_governance_v2.json"
        
    def load_risk_metrics(self) -> Dict[str, Any]:
        """Load latest FDI and CS values from risk assessment."""
        if not self.forecast_risk_path.exists():
            raise FileNotFoundError(f"Risk assessment not found: {self.forecast_risk_path}")
        
        with open(self.forecast_risk_path, 'r') as f:
            data = json.load(f)
        
        return {
            'fdi': data['forecast_evaluation']['forecast_deviation_index']['value'],
            'cs': data['forecast_evaluation']['confidence_stability']['value'],
            'overall_risk': data['risk_levels']['overall_risk']
        }
    
    def load_predictive_metrics(self) -> Dict[str, Any]:
        """Load predicted integrity and confidence from predictive engine output."""
        if not self.predictive_metrics_path.exists():
            raise FileNotFoundError(f"Predictive metrics not found: {self.predictive_metrics_path}")
        
        with open(self.predictive_metrics_path, 'r') as f:
            data = json.load(f)
        
        return {
            'predicted_integrity': data['predictions']['integrity']['predicted_mean'],
            'confidence': data['predictions']['integrity']['confidence']
        }
    
    def compute_learning_rate_factor(self, fdi: float, cs: float) -> Tuple[float, str, str]:
        """
        Compute learning rate adjustment factor based on FDI and CS.
        
        Returns:
            (lr_factor, fdi_status, cs_status)
        """
        # Determine FDI status
        if fdi < self.FDI_EXCELLENT:
            fdi_status = "excellent"
            fdi_factor = self.LR_FACTOR_EXCELLENT
        elif fdi < self.FDI_GOOD:
            fdi_status = "good"
            fdi_factor = self.LR_FACTOR_GOOD
        elif fdi < self.FDI_WARNING:
            fdi_status = "drifting"
            fdi_factor = self.LR_FACTOR_DRIFTING
        else:
            fdi_status = "critical"
            fdi_factor = self.LR_FACTOR_CRITICAL
        
        # Determine CS status
        if cs < self.CS_STABLE:
            cs_status = "stable"
            cs_penalty = 0.0
        elif cs < self.CS_UNSTABLE:
            cs_status = "moderate"
            cs_penalty = 0.1  # 10% reduction
        else:
            cs_status = "unstable"
            cs_penalty = 0.2  # 20% reduction
        
        # Combined learning rate factor
        lr_factor = fdi_factor * (1.0 - cs_penalty)
        
        return round(lr_factor, 3), fdi_status, cs_status
    
    def check_alert_conditions(self, fdi: float, cs: float, predicted_integrity: float) -> list:
        """Check if any alert conditions are triggered."""
        alerts = []
        
        if fdi >= self.FDI_WARNING:
            alerts.append({
                'type': 'fdi_warning',
                'severity': 'high' if fdi >= 20.0 else 'medium',
                'message': f'Forecast Deviation Index ({fdi}%) exceeds warning threshold ({self.FDI_WARNING}%)',
                'recommendation': 'Review predictive model features and recalibrate'
            })
        
        if cs >= self.CS_UNSTABLE:
            alerts.append({
                'type': 'cs_unstable',
                'severity': 'medium',
                'message': f'Confidence Stability ({cs}) indicates unstable variance',
                'recommendation': 'Review model input quality and feature consistency'
            })
        
        if predicted_integrity < 90.0:
            alerts.append({
                'type': 'integrity_degradation',
                'severity': 'critical',
                'message': f'Predicted integrity ({predicted_integrity}%) below minimum threshold (90%)',
                'recommendation': 'Emergency review required - integrity at risk'
            })
        
        return alerts
    
    def generate_control_output(self) -> Dict[str, Any]:
        """Main execution: load metrics, compute adjustments, check alerts."""
        # Load current risk metrics
        risk = self.load_risk_metrics()
        predictive = self.load_predictive_metrics()
        
        # Compute learning rate adjustment
        lr_factor, fdi_status, cs_status = self.compute_learning_rate_factor(
            risk['fdi'], 
            risk['cs']
        )
        
        # Check for alert conditions
        alerts = self.check_alert_conditions(
            risk['fdi'],
            risk['cs'],
            predictive['predicted_integrity']
        )
        
        # Generate output
        output = {
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'controller_version': '2.0.0',
            'risk_inputs': {
                'fdi': risk['fdi'],
                'fdi_status': fdi_status,
                'cs': risk['cs'],
                'cs_status': cs_status,
                'overall_risk': risk['overall_risk']
            },
            'predictive_inputs': {
                'predicted_integrity': predictive['predicted_integrity'],
                'confidence': predictive['confidence']
            },
            'control_outputs': {
                'learning_rate_factor': lr_factor,
                'adjustment_reason': f'FDI={fdi_status}, CS={cs_status}',
                'recommended_audit_frequency': '7d' if lr_factor >= 1.0 else '3d'
            },
            'alerts': alerts,
            'alert_count': len(alerts),
            'status': 'nominal' if len(alerts) == 0 else 'alert_triggered'
        }
        
        return output
    
    def save_output(self, output: Dict[str, Any]):
        """Save controller output to reports directory."""
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.output_path, 'w') as f:
            json.dump(output, f, indent=2)
        
        print(f"✅ Adaptive Controller v2 output saved: {self.output_path}")
        print(f"   Learning Rate Factor: {output['control_outputs']['learning_rate_factor']}")
        print(f"   Alert Count: {output['alert_count']}")
        print(f"   Status: {output['status']}")
    
    def run(self):
        """Execute adaptive controller and save results."""
        try:
            output = self.generate_control_output()
            self.save_output(output)
            
            # Return non-zero exit code if alerts triggered
            return 1 if output['alert_count'] > 0 else 0
            
        except Exception as e:
            print(f"❌ Adaptive Controller v2 failed: {e}", file=sys.stderr)
            return 2


def main():
    """CLI entry point."""
    workspace = Path(__file__).parent.parent.parent
    controller = AdaptiveControllerV2(workspace)
    sys.exit(controller.run())


if __name__ == '__main__':
    main()
