import os
from unittest.mock import *

import yaml
import pytest

from mlagents.trainers import ActionInfo
from mlagents.trainers import TrainerMetrics
from mlagents.trainers.trainer_controller import TrainerController
from mlagents.trainers.ppo.trainer import PPOTrainer
from mlagents.trainers.bc.offline_trainer import OfflineBCTrainer
from mlagents.trainers.bc.online_trainer import OnlineBCTrainer
from mlagents.envs.subprocess_env_manager import StepInfo
from mlagents.envs.exception import UnityEnvironmentException
from mlagents.envs.sampler_class import SamplerManager


@pytest.fixture
def dummy_config():
    return yaml.safe_load(
        """
        default:
            trainer: ppo
            batch_size: 32
            beta: 5.0e-3
            buffer_size: 512
            epsilon: 0.2
            gamma: 0.99
            hidden_units: 128
            lambd: 0.95
            learning_rate: 3.0e-4
            max_steps: 5.0e4
            normalize: true
            num_epoch: 5
            num_layers: 2
            time_horizon: 64
            sequence_length: 64
            summary_freq: 1000
            use_recurrent: false
            memory_size: 8
            use_curiosity: false
            curiosity_strength: 0.0
            curiosity_enc_size: 1
        """
    )


@pytest.fixture
def dummy_online_bc_config():
    return yaml.safe_load(
        """
        default:
            trainer: online_bc
            brain_to_imitate: ExpertBrain
            batches_per_epoch: 16
            batch_size: 32
            beta: 5.0e-3
            buffer_size: 512
            epsilon: 0.2
            gamma: 0.99
            hidden_units: 128
            lambd: 0.95
            learning_rate: 3.0e-4
            max_steps: 5.0e4
            normalize: true
            num_epoch: 5
            num_layers: 2
            time_horizon: 64
            sequence_length: 64
            summary_freq: 1000
            use_recurrent: false
            memory_size: 8
            use_curiosity: false
            curiosity_strength: 0.0
            curiosity_enc_size: 1
        """
    )


@pytest.fixture
def dummy_offline_bc_config():
    return yaml.safe_load(
        """
        default:
            trainer: offline_bc
            demo_path: """
        + os.path.dirname(os.path.abspath(__file__))
        + """/test.demo
            batches_per_epoch: 16
            batch_size: 32
            beta: 5.0e-3
            buffer_size: 512
            epsilon: 0.2
            gamma: 0.99
            hidden_units: 128
            lambd: 0.95
            learning_rate: 3.0e-4
            max_steps: 5.0e4
            normalize: true
            num_epoch: 5
            num_layers: 2
            time_horizon: 64
            sequence_length: 64
            summary_freq: 1000
            use_recurrent: false
            memory_size: 8
            use_curiosity: false
            curiosity_strength: 0.0
            curiosity_enc_size: 1
        """
    )


@pytest.fixture
def dummy_offline_bc_config_with_override():
    base = dummy_offline_bc_config()
    base["testbrain"] = {}
    base["testbrain"]["normalize"] = False
    return base


@pytest.fixture
def dummy_bad_config():
    return yaml.safe_load(
        """
        default:
            trainer: incorrect_trainer
            brain_to_imitate: ExpertBrain
            batches_per_epoch: 16
            batch_size: 32
            beta: 5.0e-3
            buffer_size: 512
            epsilon: 0.2
            gamma: 0.99
            hidden_units: 128
            lambd: 0.95
            learning_rate: 3.0e-4
            max_steps: 5.0e4
            normalize: true
            num_epoch: 5
            num_layers: 2
            time_horizon: 64
            sequence_length: 64
            summary_freq: 1000
            use_recurrent: false
            memory_size: 8
        """
    )


@pytest.fixture
def basic_trainer_controller():
    return TrainerController(
        model_path="test_model_path",
        summaries_dir="test_summaries_dir",
        run_id="test_run_id",
        save_freq=100,
        meta_curriculum=None,
        load=True,
        train=True,
        keep_checkpoints=False,
        lesson=None,
        training_seed=99,
        fast_simulation=True,
        sampler_manager=SamplerManager(None),
        resampling_interval=None,
    )


@patch("numpy.random.seed")
@patch("tensorflow.set_random_seed")
def test_initialization_seed(numpy_random_seed, tensorflow_set_seed):
    seed = 27
    TrainerController(
        "",
        "",
        "1",
        1,
        None,
        True,
        False,
        False,
        None,
        seed,
        True,
        SamplerManager(None),
        None,
    )
    numpy_random_seed.assert_called_with(seed)
    tensorflow_set_seed.assert_called_with(seed)


def assert_bc_trainer_constructed(
    trainer_cls, input_config, tc, expected_brain_params, expected_config
):
    external_brains = {"testbrain": expected_brain_params}

    def mock_constructor(self, brain, trainer_parameters, training, load, seed, run_id):
        assert brain == expected_brain_params
        assert trainer_parameters == expected_config
        assert training == tc.train_model
        assert load == tc.load_model
        assert seed == tc.seed
        assert run_id == tc.run_id

    with patch.object(trainer_cls, "__init__", mock_constructor):
        tc.initialize_trainers(input_config, external_brains)
        assert "testbrain" in tc.trainers
        assert isinstance(tc.trainers["testbrain"], trainer_cls)


def assert_ppo_trainer_constructed(
    input_config, tc, expected_brain_params, expected_config, expected_reward_buff_cap=1
):
    external_brains = {"testbrain": expected_brain_params}

    def mock_constructor(
        self, brain, reward_buff_cap, trainer_parameters, training, load, seed, run_id
    ):
        self.trainer_metrics = TrainerMetrics("", "")
        assert brain == expected_brain_params
        assert trainer_parameters == expected_config
        assert reward_buff_cap == expected_reward_buff_cap
        assert training == tc.train_model
        assert load == tc.load_model
        assert seed == tc.seed
        assert run_id == tc.run_id

    with patch.object(PPOTrainer, "__init__", mock_constructor):
        tc.initialize_trainers(input_config, external_brains)
        assert "testbrain" in tc.trainers
        assert isinstance(tc.trainers["testbrain"], PPOTrainer)


@patch("mlagents.envs.BrainParameters")
def test_initialize_trainer_parameters_uses_defaults(BrainParametersMock):
    brain_params_mock = BrainParametersMock()
    tc = basic_trainer_controller()

    full_config = dummy_offline_bc_config()
    expected_config = full_config["default"]
    expected_config["summary_path"] = tc.summaries_dir + "/test_run_id_testbrain"
    expected_config["model_path"] = tc.model_path + "/testbrain"
    expected_config["keep_checkpoints"] = tc.keep_checkpoints

    assert_bc_trainer_constructed(
        OfflineBCTrainer, full_config, tc, brain_params_mock, expected_config
    )


@patch("mlagents.envs.BrainParameters")
def test_initialize_trainer_parameters_override_defaults(BrainParametersMock):
    brain_params_mock = BrainParametersMock()
    tc = basic_trainer_controller()

    full_config = dummy_offline_bc_config_with_override()
    expected_config = full_config["default"]
    expected_config["summary_path"] = tc.summaries_dir + "/test_run_id_testbrain"
    expected_config["model_path"] = tc.model_path + "/testbrain"
    expected_config["keep_checkpoints"] = tc.keep_checkpoints

    # Override value from specific brain config
    expected_config["normalize"] = False

    assert_bc_trainer_constructed(
        OfflineBCTrainer, full_config, tc, brain_params_mock, expected_config
    )


@patch("mlagents.envs.BrainParameters")
def test_initialize_online_bc_trainer(BrainParametersMock):
    brain_params_mock = BrainParametersMock()
    tc = basic_trainer_controller()

    full_config = dummy_online_bc_config()
    expected_config = full_config["default"]
    expected_config["summary_path"] = tc.summaries_dir + "/test_run_id_testbrain"
    expected_config["model_path"] = tc.model_path + "/testbrain"
    expected_config["keep_checkpoints"] = tc.keep_checkpoints

    assert_bc_trainer_constructed(
        OnlineBCTrainer, full_config, tc, brain_params_mock, expected_config
    )


@patch("mlagents.envs.BrainParameters")
def test_initialize_ppo_trainer(BrainParametersMock):
    brain_params_mock = BrainParametersMock()
    tc = basic_trainer_controller()

    full_config = dummy_config()
    expected_config = full_config["default"]
    expected_config["summary_path"] = tc.summaries_dir + "/test_run_id_testbrain"
    expected_config["model_path"] = tc.model_path + "/testbrain"
    expected_config["keep_checkpoints"] = tc.keep_checkpoints

    assert_ppo_trainer_constructed(full_config, tc, brain_params_mock, expected_config)


@patch("mlagents.envs.BrainParameters")
def test_initialize_invalid_trainer_raises_exception(BrainParametersMock):
    tc = basic_trainer_controller()
    bad_config = dummy_bad_config()
    external_brains = {"testbrain": BrainParametersMock()}

    with pytest.raises(UnityEnvironmentException):
        tc.initialize_trainers(bad_config, external_brains)


def trainer_controller_with_start_learning_mocks():
    trainer_mock = MagicMock()
    trainer_mock.get_step = 0
    trainer_mock.get_max_steps = 5
    trainer_mock.parameters = {"some": "parameter"}
    trainer_mock.write_tensorboard_text = MagicMock()

    tc = basic_trainer_controller()
    tc.initialize_trainers = MagicMock()
    tc.trainers = {"testbrain": trainer_mock}
    tc.advance = MagicMock()
    tc.trainers["testbrain"].get_step = 0

    def take_step_sideeffect(env):
        tc.trainers["testbrain"].get_step += 1
        if tc.trainers["testbrain"].get_step > 10:
            raise KeyboardInterrupt
        return 1

    tc.advance.side_effect = take_step_sideeffect

    tc._export_graph = MagicMock()
    tc._save_model = MagicMock()
    return tc, trainer_mock


@patch("tensorflow.reset_default_graph")
def test_start_learning_trains_forever_if_no_train_model(tf_reset_graph):
    tc, trainer_mock = trainer_controller_with_start_learning_mocks()
    tc.train_model = False

    trainer_config = dummy_config()
    tf_reset_graph.return_value = None

    env_mock = MagicMock()
    env_mock.close = MagicMock()
    env_mock.reset = MagicMock()
    env_mock.external_brains = MagicMock()

    tc.start_learning(env_mock, trainer_config)
    tf_reset_graph.assert_called_once()
    tc.initialize_trainers.assert_called_once_with(
        trainer_config, env_mock.external_brains
    )
    env_mock.reset.assert_called_once()
    assert tc.advance.call_count == 11
    tc._export_graph.assert_not_called()
    tc._save_model.assert_not_called()
    env_mock.close.assert_called_once()


@patch("tensorflow.reset_default_graph")
def test_start_learning_trains_until_max_steps_then_saves(tf_reset_graph):
    tc, trainer_mock = trainer_controller_with_start_learning_mocks()
    trainer_config = dummy_config()
    tf_reset_graph.return_value = None

    brain_info_mock = MagicMock()
    env_mock = MagicMock()
    env_mock.close = MagicMock()
    env_mock.reset = MagicMock(return_value=brain_info_mock)
    env_mock.external_brains = MagicMock()

    tc.start_learning(env_mock, trainer_config)
    tf_reset_graph.assert_called_once()
    tc.initialize_trainers.assert_called_once_with(
        trainer_config, env_mock.external_brains
    )
    env_mock.reset.assert_called_once()
    assert tc.advance.call_count == trainer_mock.get_max_steps + 1
    env_mock.close.assert_called_once()
    tc._save_model.assert_called_once()


def test_start_learning_updates_meta_curriculum_lesson_number():
    tc, trainer_mock = trainer_controller_with_start_learning_mocks()
    trainer_config = dummy_config()

    brain_info_mock = MagicMock()
    env_mock = MagicMock()
    env_mock.close = MagicMock()
    env_mock.reset = MagicMock(return_value=brain_info_mock)

    meta_curriculum_mock = MagicMock()
    meta_curriculum_mock.set_all_curriculums_to_lesson_num = MagicMock()
    tc.meta_curriculum = meta_curriculum_mock
    tc.lesson = 5

    tc.start_learning(env_mock, trainer_config)
    meta_curriculum_mock.set_all_curriculums_to_lesson_num.assert_called_once_with(
        tc.lesson
    )


def trainer_controller_with_take_step_mocks():
    trainer_mock = MagicMock()
    trainer_mock.get_step = 0
    trainer_mock.get_max_steps = 5
    trainer_mock.parameters = {"some": "parameter"}
    trainer_mock.write_tensorboard_text = MagicMock()

    tc = basic_trainer_controller()
    tc.trainers = {"testbrain": trainer_mock}

    return tc, trainer_mock


def test_take_step_adds_experiences_to_trainer_and_trains():
    tc, trainer_mock = trainer_controller_with_take_step_mocks()

    old_step_info = StepInfo(Mock(), Mock(), MagicMock())
    new_step_info = StepInfo(Mock(), Mock(), MagicMock())
    trainer_mock.is_ready_update = MagicMock(return_value=True)

    env_mock = MagicMock()
    env_mock.step.return_value = [new_step_info]
    env_mock.reset.return_value = [old_step_info]
    env_mock.global_done = False

    tc.advance(env_mock)
    env_mock.reset.assert_not_called()
    env_mock.step.assert_called_once()
    trainer_mock.add_experiences.assert_called_once_with(
        new_step_info.previous_all_brain_info,
        new_step_info.current_all_brain_info,
        new_step_info.brain_name_to_action_info["testbrain"].outputs,
    )
    trainer_mock.process_experiences.assert_called_once_with(
        new_step_info.previous_all_brain_info, new_step_info.current_all_brain_info
    )
    trainer_mock.update_policy.assert_called_once()
    trainer_mock.increment_step.assert_called_once()
