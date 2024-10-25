from time import time

import os
import numpy as np
import torch
import torch.nn.functional as F

from tqdm import tqdm
from torch import nn
from torch.autograd import Variable

# Check for CUDA support.

CUDA_AVAILABLE = torch.cuda.is_available()
device = torch.device("cuda:0") if CUDA_AVAILABLE else torch.device("cpu")


def train(
    network_factory,
    training_spectra,
    training_labels,
    validation_spectra,
    validation_labels,
    test_spectra,
    test_labels,
    class_names=None,
    learning_rate=1e-4,
    weight_decay=1e-5,
    num_epochs=200,
    batch_size=100,
    task=None,
):
    """
    Train a neural network to classify stellar sources.

    :param network_factory:
        The neural network class to use. This should be an object from `astra.contrib.classifier.networks`.

    :param training_spectra:
        An array of shape (N, P) training set fluxes to use, where N is the number of sources and P is the number of pixels.

    :param training_labels:
        An array of training set labels to use. This should be shape (N, L), where L is the number of labels.

    :param validation_spectra:
        An array of validation set fluxes to use.

    :param validation_labels:
        An array of validation set labels to use.

    :param test_spectra:
        An array of test set fluxes to use.

    :param test_labels:
        An array of test set labels to use.

    :param class_names: (optional)
        A tuple of class names for different objects.

    :param learning_rate: (optional)
        The learning rate to use during training (default: 1e-4).

    :param weight_decay: (optional)
        The weight decay to use during training (default: 1e-5).

    :param num_epochs: (optional)
        The number of epochs to use during training (default: 200).

    :param batch_size: (optional)
        The number of sources to use per batch.

    :param task: (optional)
        If supplied, then progress messages will be sent back via this task.
    """

    n_training_set = training_spectra.shape[0]
    n_validation_set = validation_spectra.shape[0]
    n_test_set = test_spectra.shape[0]

    n_unique_classes = len(set(training_labels))
    weight_imbalance = np.array(
        [np.sum(training_labels == j) / n_training_set for j in range(n_unique_classes)]
    )

    print(f"Weight imbalance: {weight_imbalance}")

    weights = torch.Tensor(1.0 / weight_imbalance)
    print(f"Inverse weight imbalance: {weights}")

    # if CUDA_AVAILABLE:
    #    weights = weights.cuda()

    criterion = nn.CrossEntropyLoss(weight=weights)

    network = network_factory(nb_classes=n_unique_classes)
    # if CUDA_AVAILABLE:
    #    network = network.cuda()

    optimizer = torch.optim.Adam(
        network.parameters(), lr=learning_rate, weight_decay=weight_decay
    )

    n_batch = int(n_training_set / batch_size)

    t = time()

    for epoch in range(num_epochs):

        status_message = []
        status_message.append("=" * 15)
        status_message.append(f"Epoch {epoch} of {num_epochs}")

        total, correct, losses = (0, 0, 0)

        total_per_class = np.zeros(n_unique_classes)
        correct_per_class = np.zeros(n_unique_classes)

        for i in tqdm(range(n_batch), total=n_batch):

            idx = np.random.choice(n_training_set, batch_size, replace=False)
            batch_labels = training_labels[idx]
            batch_spectra = training_spectra[idx]

            batch = torch.Tensor(batch_spectra)
            # if CUDA_AVAILABLE:
            #    batch = batch.cuda()

            optimizer.zero_grad()

            pred = network.forward(Variable(batch))

            y = torch.LongTensor(batch_labels)
            y_var = Variable(y)
            # if CUDA_AVAILABLE:
            #    y_var = y_var.cuda()

            loss = criterion(pred, y_var)
            loss.backward()

            optimizer.step()

            losses += loss.item()

            _, preds = torch.max(pred.data.cpu(), 1)

            total += batch_size
            correct += (preds == y).sum().item()

            for j in range(n_unique_classes):
                idx_class = np.argwhere(batch_labels == j)
                idx_class = idx_class.reshape(idx_class.shape[0])

                total_per_class[j] += idx_class.size
                correct_per_class[j] += (preds[idx_class] == j).sum().item()

        status_message.append(
            f"Training loss: {losses/n_batch:4f}, time: {(time() - t)/60:.1f} min"
        )
        status_message.append(f"Training accuracy: {100 * correct/total:.2f}%")
        for j in range(n_unique_classes):
            class_str = f"{j}" if class_names is None else f"{j} ({class_names[j]})"
            status_message.append(
                f"\tClass {class_str}: {100 * correct_per_class[j] / total_per_class[j]:.2f}%"
            )

        # Validate.
        with torch.no_grad():
            status_message.append("-" * 10)

            batch = torch.Tensor(validation_spectra)
            # if CUDA_AVAILABLE:
            #    batch = batch.cuda()
            pred = network.forward(Variable(batch))

            y = torch.LongTensor(validation_labels)
            y_var = Variable(y)
            # if CUDA_AVAILABLE:
            #    y_var = y_var.cuda()
            validation_loss = criterion(pred, y_var)
            _, preds = torch.max(pred.data.cpu(), 1)

            validation_total = n_validation_set
            validation_correct = (preds == y).sum().item()

            validation_total_per_class = np.zeros(n_unique_classes)
            validation_correct_per_class = np.zeros(n_unique_classes)

            for j in range(n_unique_classes):
                idx_class = np.argwhere(validation_labels == j)
                idx_class = idx_class.reshape(idx_class.shape[0])

                validation_total_per_class += idx_class.size
                validation_correct_per_class += (preds[idx_class] == j).sum().item()

            status_message.append(f"Validation loss: {validation_loss:.4f}")
            status_message.append(
                f"Validation accuracy: {100 * validation_correct/validation_total:.2f}%"
            )
            for j in range(n_unique_classes):
                class_str = f"{j}" if class_names is None else f"{j} ({class_names[j]})"
                status_message.append(
                    f"\tClass {class_str}: {100 * correct_per_class[j] / total_per_class[j]:.2f}%"
                )
            status_message.append("-" * 10)

        # Test.
        batch = torch.Tensor(test_spectra)
        # if CUDA_AVAILABLE:
        #    batch = batch.cuda()
        pred = network.forward(Variable(batch))

        y = torch.LongTensor(test_labels)
        y_var = Variable(y)
        # if CUDA_AVAILABLE:
        #    y_var = y_var.cuda()

        test_loss = criterion(pred, y_var)
        _, preds = torch.max(pred.data.cpu(), 1)

        test_total = n_test_set
        test_correct = (preds == y).sum().item()

        test_total_per_class = np.zeros(n_unique_classes)
        test_correct_per_class = np.zeros(n_unique_classes)

        for j in range(n_unique_classes):
            idx_class = np.argwhere(test_labels == j)
            idx_class = idx_class.reshape(idx_class.shape[0])

            test_total_per_class[j] += idx_class.size
            test_correct_per_class[j] += (preds[idx_class] == j).sum().item()

        status_message.append(f"Test loss: {test_loss:.4f}")
        status_message.append(f"Test accuracy: {100 * test_correct / test_total:.2f}%")
        for j in range(n_unique_classes):
            class_str = f"{j}" if class_names is None else f"{j} ({class_names[j]})"
            status_message.append(
                f"\tClass {class_str}: {100 * test_correct_per_class[j] / test_total_per_class[j]:.2f}%"
            )

        status_message.append("=" * 15)

        print("\n".join(status_message))

    state = dict(
        epoch=epoch,
        losses=(loss, validation_loss, test_loss),
        class_names=class_names,
        weight_decay=weight_decay,
        learning_rate=learning_rate,
        batch_size=batch_size,
    )
    return (state, network, optimizer)


def predict_classes(network, spectra):
    """
    Predict an object class given a trained network and some spectra.
    """
    net = torch.load(model_path)
    batch = torch.Tensor(spectra)
    # if CUDA_AVAILABLE:
    #    batch = batch.cuda()

    pred = net.forward(Variable(batch))
    _, preds = torch.max(pred.data.cpu(), 1)

    return preds.numpy()
