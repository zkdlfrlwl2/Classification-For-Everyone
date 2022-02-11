import os
import sys
import pytorch_lightning as pl
from pytorch_lightning.utilities.seed import seed_everything
import torch
import torch.nn as nn
import torch.optim as optim
from torch.optim.lr_scheduler import ReduceLROnPlateau
from pytorch_lightning.callbacks import (
    EarlyStopping,
    TQDMProgressBar,
)
from pytorch_lightning.loggers import WandbLogger
from torchmetrics import Accuracy

import datamodule
from model import MobileNetV3

sys.path.insert(1, os.path.abspath('..'))
import utils


class MobileNetV3Model(pl.LightningModule):

    def __init__(
            self,
            config,
    ):
        super().__init__()
        self.save_hyperparameters()

        self.model = MobileNetV3(
            image_channels=self.hparams.config.image_channels,
            n_classes=self.hparams.config.n_classes,
            alpha=self.hparams.config.alpha,
            model_size=self.hparams.config.model_size,
            bneck_size=self.hparams.config.bneck_size,
            dropout_rate=self.hparams.config.dropout_rate
        )

        self.model.initialize_weights()

        self.loss = nn.CrossEntropyLoss()
        self.accuracy = Accuracy()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.model(x)

    def step(self, batch):
        x, y = batch
        logit = self(x)
        loss = self.loss(logit, y)
        preds = torch.argmax(logit, dim=1)
        acc = self.accuracy(preds, y)
        return loss, acc

    def training_step(self, batch, batch_idx) -> torch.Tensor:
        loss, acc = self.step(batch)
        self.log('train_loss', loss, prog_bar=True)
        self.log('train_acc', acc, prog_bar=True)
        return loss

    def validation_step(self, batch, batch_idx) -> torch.Tensor:
        loss, acc = self.step(batch)
        self.log('val_loss', loss, prog_bar=True)
        self.log('val_acc', acc, prog_bar=True)
        return loss

    def test_step(self, batch, batch_idx) -> torch.Tensor:
        loss, acc = self.step(batch)
        self.log('test_loss', loss, prog_bar=True)
        self.log('test_acc', acc, prog_bar=True)
        return loss

    def configure_optimizers(self):
        optimizer = optim.Adam(
            self.parameters(),
            lr=self.hparams.config.lr,
            weight_decay=self.hparams.config.weight_decay,
        )
        scheduler_dict = {
            'scheduler': ReduceLROnPlateau(
                optimizer,
                mode='min',
                factor=self.hparams.config.scheduler_factor,
                patience=self.hparams.config.scheduler_patience,
                verbose=True,
            ),
            'monitor': 'val_loss',
        }
        return {'optimizer': optimizer, 'lr_scheduler': scheduler_dict}


def train():
    # Hyperparameters
    config = utils.get_config()
    seed_everything(config.seed)

    # Dataloader
    if config.dataset == 'CIFAR10':
        dm = datamodule.CIFAR10DataModule(
            config.data_dir,
            image_size=config.image_size,
            batch_size=config.batch_size,
            rho=config.rho
        )
    else:
        dm = datamodule.CIFAR100DataModule(
            config.data_dir,
            image_size=config.image_size,
            batch_size=config.batch_size,
            rho=config.rho
        )

    # Model
    mobilenetv3 = MobileNetV3Model(config=config)

    # Logger
    wandb_logger = WandbLogger(
        name=f'{config.project_name}-{config.dataset}',
        project=config.project_name,
        save_dir=config.save_dir,
        log_model='all',
    )

    wandb_logger.watch(mobilenetv3, log='all', log_freq=100)

    # Trainer setting
    callbacks = [
        EarlyStopping(
            monitor='val_acc',
            min_delta=0.00,
            patience=config.earlystopping_patience,
            verbose=True,
            mode='max',
        ),
        TQDMProgressBar(refresh_rate=10),
    ]

    trainer: pl.Trainer = pl.Trainer(
        logger=wandb_logger,
        gpus=1,
        max_epochs=config.epochs,
        callbacks=callbacks,
    )

    # Train
    trainer.fit(mobilenetv3, datamodule=dm)
    trainer.test(mobilenetv3, datamodule=dm)

    # Finish
    wandb_logger.experiment.unwatch(mobilenetv3)

    # Model to Torchscript
    saved_model_path = utils.model_save(
        mobilenetv3,
        config.torchscript_model_save_path,
        config.project_name+config.model_size
    )

    # Save artifacts
    wandb_logger.experiment.save(saved_model_path)


if __name__=='__main__':
    train()