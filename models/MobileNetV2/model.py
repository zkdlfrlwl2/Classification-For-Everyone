import torch
import torch.nn as nn
import numpy as np
from .block import ConvBlock, BottleNeck, Classifier


class MobileNetV2(nn.Module):

    def __init__(
            self,
            image_channels: int,
            n_classes: int,
            alpha: float = 1.0,
    ) -> None:
        super().__init__()
        self.alpha = alpha

        self.feature_extractor = nn.Sequential(
            ConvBlock(
                in_channels=image_channels,
                out_channels=self._multiply_width(32),
                kernel_size=3,
                stride=2,
                padding=1
            ),
            nn.BatchNorm2d(num_features=self._multiply_width(32)),
            nn.ReLU6(),
            BottleNeck(
                dim=[self._multiply_width(32), self._multiply_width(16)],
                factor=1,
                iterate=1,
                stride=1,
            ),
            BottleNeck(
                dim=[self._multiply_width(16), self._multiply_width(24)],
                factor=6,
                iterate=2,
                stride=2,
            ),
            BottleNeck(
                dim=[self._multiply_width(24), self._multiply_width(32)],
                factor=6,
                iterate=3,
                stride=2,
            ),
            BottleNeck(
                dim=[self._multiply_width(32), self._multiply_width(64)],
                factor=6,
                iterate=4,
                stride=2,
            ),
            BottleNeck(
                dim=[self._multiply_width(64), self._multiply_width(96)],
                factor=6,
                iterate=3,
                stride=1,
            ),
            BottleNeck(
                dim=[self._multiply_width(96), self._multiply_width(160)],
                factor=6,
                iterate=3,
                stride=2,
            ),
            BottleNeck(
                dim=[self._multiply_width(160), self._multiply_width(320)],
                factor=6,
                iterate=1,
                stride=1,
            ),
            ConvBlock(
                in_channels=self._multiply_width(320),
                out_channels=self._multiply_width(1280),
                kernel_size=1,
            ),
            nn.BatchNorm2d(num_features=self._multiply_width(1280)),
            nn.ReLU6(),
            nn.AdaptiveAvgPool2d(1),
        )
        self.classifier = Classifier(
            in_features=self._multiply_width(1280),
            out_features=n_classes
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.feature_extractor(x)
        x = torch.flatten(x, 1)
        logits = self.classifier(x)
        return logits

    def initialize_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(
                    m.weight,
                    mode='fan_out',
                    nonlinearity='relu',
                )
            elif isinstance(m, nn.BatchNorm2d):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)
            elif isinstance(m, nn.Linear):
                nn.init.normal_(m.weight, 0, 0.01)
                nn.init.constant_(m.bias, 0)

    def _multiply_width(self, dim: int) -> int:
        return int(np.ceil(self.alpha*dim))