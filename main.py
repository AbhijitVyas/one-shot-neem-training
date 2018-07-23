import numpy as np
import random
import tensorflow as tf
import logging
import imageio
import uuid

from neem_data_generator import NEEM, NEEMDataGenerator as DataGenerator
from mil import MIL
from tensorflow.python.platform import flags

FLAGS = flags.FLAGS
LOGGER = logging.getLogger(__name__)

flags.DEFINE_integer('number_of_shot', 1, 'number of examples used for inner gradient update (K for K-shot learning).')
flags.DEFINE_integer('number_of_shot_train', -1, 'number of examples used for gradient update during training (use if you want to test with a different number).')
flags.DEFINE_integer('number_of_shot_test', 1, 'number of demos used during test time')

flags.DEFINE_integer('metatrain_iterations', 1, 'number of metatraining iterations.')
flags.DEFINE_integer('meta_batch_size', 1, 'number of tasks sampled per meta-update')
flags.DEFINE_float('meta_lr', 0.001, 'the base learning rate of the generator')
flags.DEFINE_integer('TimeFrame', 100, 'time horizon of the demo videos')
flags.DEFINE_integer('end_test_set_size', 1, 'size of the test set, 150 for sim_reach and 76 for sim push')
flags.DEFINE_integer('all_set_size', 1000, 'size of whole set')

flags.DEFINE_bool('clip', False, 'use gradient clipping for fast gradient')
flags.DEFINE_float('clip_max', 10.0, 'maximum clipping value for fast gradient')
flags.DEFINE_float('clip_min', -10.0, 'minimum clipping value for fast gradient')
flags.DEFINE_bool('fc_bt', True, 'use bias transformation for the first fc layer')
flags.DEFINE_bool('all_fc_bt', False, 'use bias transformation for all fc layers')
flags.DEFINE_bool('conv_bt', True, 'use bias transformation for the first conv layer, N/A for using pretraining')
flags.DEFINE_integer('bt_dim', 10, 'the dimension of bias transformation for FC layers')
flags.DEFINE_string('pretrain_weight_path', 'N/A', 'path to pretrained weights')
flags.DEFINE_bool('train_pretrain_conv1', False, 'whether to finetune the pretrained weights')
flags.DEFINE_bool('two_head', False, 'use two-head architecture')
flags.DEFINE_bool('learn_final_eept', False, 'learn an auxiliary loss for predicting final end-effector pose')
flags.DEFINE_bool('learn_final_eept_whole_traj', False, 'learn an auxiliary loss for predicting final end-effector pose \
                                                         by passing the whole trajectory of eepts (used for video-only models)')
flags.DEFINE_bool('stopgrad_final_eept', True, 'stop the gradient when concatenate the predicted final eept with the feature points')
flags.DEFINE_integer('final_eept_min', 6, 'first index of the final eept in the action array')
flags.DEFINE_integer('final_eept_max', 8, 'last index of the final eept in the action array')
flags.DEFINE_float('final_eept_loss_eps', 0.1, 'the coefficient of the auxiliary loss')
flags.DEFINE_float('act_loss_eps', 1.0, 'the coefficient of the action loss')
flags.DEFINE_float('loss_multiplier', 50.0, 'the constant multiplied with the loss value, 100 for reach and 50 for push')
flags.DEFINE_bool('use_l1_l2_loss', False, 'use a loss with combination of l1 and l2')
flags.DEFINE_float('l2_eps', 0.01, 'coeffcient of l2 loss')
flags.DEFINE_bool('shuffle_val', False, 'whether to choose the validation set via shuffling or not')
flags.DEFINE_bool('fp', True, 'use spatial soft-argmax or not')

flags.DEFINE_bool('no_action', False, 'do not include actions in the demonstrations for inner update')
flags.DEFINE_bool('no_state', False, 'do not include states in the demonstrations during training')
flags.DEFINE_bool('no_final_eept', False, 'do not include final ee pos in the demonstrations for inner update')
flags.DEFINE_bool('zero_state', False, 'zero-out states (meta-learn state) in the demonstrations for inner update (used in the paper with video-only demos)')
flags.DEFINE_bool('two_arms', False, 'use two-arm structure when state is zeroed-out')

flags.DEFINE_string('prologquery', 'A is 1.', 'neem set in openease')
flags.DEFINE_string('neems', '/episodes/Playing-In-Kitchen', 'neem set in openease')
flags.DEFINE_string('local_model_path', '/media/asil/Tuna/episodes/Playing-In-Kitchen', 'neem set in openease')
flags.DEFINE_integer('im_width', 125, 'width of the images in the demo videos,  125 for sim_push, and 80 for sim_vision_reach')
flags.DEFINE_integer('im_height', 125, 'height of the images in the demo videos, 125 for sim_push, and 64 for sim_vision_reach')
flags.DEFINE_integer('num_channels', 3, 'number of channels of the images in the demo videos')
flags.DEFINE_integer('num_fc_layers', 3, 'number of fully-connected layers')
flags.DEFINE_integer('layer_size', 100, 'hidden dimension of fully-connected layers')
flags.DEFINE_bool('temporal_conv_2_head', False, 'whether or not to use temporal convolutions for the two-head architecture in video-only setting.')
flags.DEFINE_bool('temporal_conv_2_head_ee', False, 'whether or not to use temporal convolutions for the two-head architecture in video-only setting for predicting the ee pose.')
flags.DEFINE_integer('temporal_filter_size', 5, 'filter size for temporal convolution')
flags.DEFINE_integer('temporal_num_filters', 64, 'number of filters for temporal convolution')
flags.DEFINE_integer('temporal_num_filters_ee', 64, 'number of filters for temporal convolution for ee pose prediction')
flags.DEFINE_integer('temporal_num_layers', 3, 'number of layers for temporal convolution for ee pose prediction')
flags.DEFINE_integer('temporal_num_layers_ee', 3, 'number of layers for temporal convolution for ee pose prediction')
flags.DEFINE_string('init', 'random', 'initializer for conv weights. Choose among random, xavier, and he')
flags.DEFINE_bool('max_pool', False, 'Whether or not to use max pooling rather than strided convolutions')
flags.DEFINE_bool('stop_grad', False, 'if True, do not use second derivatives in meta-optimization (for speed)')

flags.DEFINE_string('experiment', 'agents-playing-things', 'experiment path relative to neem')

flags.DEFINE_integer('random_seed', 0, 'random seed for training')
flags.DEFINE_float('gpu_memory_fraction', 0.6, 'fraction of memory used in gpu')
flags.DEFINE_float('train_update_lr', 1e-2, 'step size alpha for inner gradient update.') # 0.001 for reaching, 0.01 for pushing and placing
flags.DEFINE_integer('num_updates', 1, 'number of inner gradient updates during training.') # 5 for placing
flags.DEFINE_integer('num_filters', 16, 'number of filters for conv nets -- 64 for placing, 16 for pushing, 40 for reaching.')
flags.DEFINE_string('norm', 'layer_norm', 'batch_norm, layer_norm, or None')
flags.DEFINE_bool('dropout', False, 'use dropout for fc layers or not')
flags.DEFINE_float('keep_prob', 0.5, 'keep probability for dropout')
flags.DEFINE_integer('filter_size', 5, 'filter size for conv nets -- 3 for placing, 5 for pushing, 3 for reaching.')
flags.DEFINE_integer('num_conv_layers', 4, 'number of conv layers -- 5 for placing, 4 for pushing, 3 for reaching.')
flags.DEFINE_integer('num_strides', 4, 'number of conv layers with strided filters -- 3 for placing, 4 for pushing, 3 for reaching.')
flags.DEFINE_bool('conv', True, 'whether or not to use a convolutional network, only applicable in some cases')
flags.DEFINE_bool('record_gifs', True, 'record gifs during evaluation')

flags.DEFINE_bool('train', True, 'training or testing')

def train(graph, model, saver, sess, data_generator, log_dir):
    """
    Train the model.
    """
    PRINT_INTERVAL = 100
    TEST_PRINT_INTERVAL = PRINT_INTERVAL*5
    SUMMARY_INTERVAL = 100
    SAVE_INTERVAL = 1000
    TOTAL_ITERS = FLAGS.metatrain_iterations
    prelosses, postlosses = [], []
    save_dir = log_dir + '/model'
    train_writer = tf.summary.FileWriter(log_dir, graph)
    training_range = range(TOTAL_ITERS)
    for itr in training_range:
        state, tgt_mu = data_generator.generate_data_batch(itr)

        print state.shape

        statea = state[:, :FLAGS.number_of_shot*FLAGS.TimeFrame, :]
        stateb = state[:, FLAGS.number_of_shot*FLAGS.TimeFrame:, :]
        actiona = tgt_mu[:, :FLAGS.number_of_shot*FLAGS.TimeFrame, :]
        actionb = tgt_mu[:, FLAGS.number_of_shot*FLAGS.TimeFrame:, :]

        feed_dict = {model.statea: statea,
                    model.stateb: stateb,
                    model.actiona: actiona,
                    model.actionb: actionb}
        input_tensors = [model.train_op]
        if itr % SUMMARY_INTERVAL == 0 or itr % PRINT_INTERVAL == 0:
            input_tensors.extend([model.train_summ_op, model.total_loss1, model.total_losses2[model.num_updates-1]])
        with graph.as_default():
            results = sess.run(input_tensors, feed_dict=feed_dict)
        if itr != 0 and itr % SUMMARY_INTERVAL == 0:
            prelosses.append(results[-2])
            train_writer.add_summary(results[-3], itr)
            postlosses.append(results[-1])
        if itr != 0 and itr % PRINT_INTERVAL == 0:
            print 'Iteration %d: average preloss is %.2f, average postloss is %.2f' % (itr, np.mean(prelosses), np.mean(postlosses))
            prelosses, postlosses = [], []

        if itr != 0 and itr % TEST_PRINT_INTERVAL == 0:
            if FLAGS.val_set_size > 0:
                input_tensors = [model.val_summ_op, model.val_total_loss1, model.val_total_losses2[model.num_updates-1]]
                val_state, val_act = data_generator.generate_data_batch(itr, train=False)
                statea = val_state[:, :FLAGS.number_of_shot*FLAGS.TimeFrame, :]
                stateb = val_state[:, FLAGS.number_of_shot*FLAGS.TimeFrame:, :]
                actiona = val_act[:, :FLAGS.number_of_shot*FLAGS.TimeFrame, :]
                actionb = val_act[:, FLAGS.number_of_shot*FLAGS.TimeFrame:, :]
                feed_dict = {model.statea: statea,
                            model.stateb: stateb,
                            model.actiona: actiona,
                            model.actionb: actionb}
                with graph.as_default():
                    results = sess.run(input_tensors, feed_dict=feed_dict)
                train_writer.add_summary(results[0], itr)
                print 'Test results: average preloss is %.2f, average postloss is %.2f' % (np.mean(results[1]), np.mean(results[2]))

        if itr != 0 and (itr % SAVE_INTERVAL == 0 or itr == training_range[-1]):
            print 'Saving model to: %s' % (save_dir + '_%d' % itr)
            with graph.as_default():
                saver.save(sess, save_dir + '_%d' % itr)

def generate_test_demos(data_generator, network_config):
    demos = data_generator.allepisodes.traj
    indices = data_generator.alltestepisodes.indices
    path = data_generator.alltestepisodes.paths

    Us = []
    Xs = []
    Os = []
    #all_filenames = []
    for i in xrange(FLAGS.end_test_set_size):
        Us.append(demos[indices[i][0]]['demoU'][indices[i][1]])
        Xs.append(demos[indices[i][0]]['demoX'][indices[i][1]])

        O = np.array(imageio.mimread(paths[i]))[:, :, :, :3]
        O = np.transpose(O, [0, 3, 2, 1]) # transpose to mujoco setting for images
        O = O.reshape(FLAGS.T, -1) / 255.0 # normalize

        Os.append(O)

        #all_filenames.append(path[indices[i][0]][indices[i][1]])
        #pose_size = len(demos[i].pose)
        #velocity_size = len(demos[i].velocity)

        #for j in xrange(0, pose_size, FLAGS.number_of_shot_test)
        #    pose = []
        #    for k in xrange(FLAGS.number_of_shot_test)
        #        pose.append(demos[i].pose[j+k].x)
        #        pose.append(demos[i].pose[j+k].y)
        #        pose.append(demos[i].pose[j+k].z)
        #        pose.append(demos[i].pose[j+k].qw)
        #        pose.append(demos[i].pose[j+k].qx)
        #        pose.append(demos[i].pose[j+k].qy)
        #        pose.append(demos[i].pose[j+k].qz)
        #    X.append(pose)

        #for j in xrange(0, pose_size, FLAGS.number_of_shot_test)
        #    velocity = []
        #    for k in xrange(FLAGS.number_of_shot_test)
        #        velocity.append(demos[i].velocity[j+k].x)
        #        velocity.append(demos[i].velocity[j+k].y)
        #        velocity.append(demos[i].velocity[j+k].z)
        #        velocity.append(demos[i].velocity[j+k].qw)
        #        velocity.append(demos[i].velocity[j+k].qx)
        #        velocity.append(demos[i].velocity[j+k].qy)
        #        velocity.append(demos[i].velocity[j+k].qz)
        #    U.append(velocity)

    #batch_image_size = FLAGS.number_of_shot_test

    #im_height = network_config['image_height']
    #im_width = network_config['image_width']
    #num_channels = network_config['image_channels']

    #all_filenames = path
    # make queue for tensorflow to read from
    #filename_queue = tf.train.string_input_producer(tf.convert_to_tensor(all_filenames), shuffle=False)

    #print 'Generating image processing ops'
    #image_reader = tf.WholeFileReader()
    #_, image_file = image_reader.read(filename_queue)
    #image = tf.image.decode_gif(image_file)
    # should be T x C x W x H
    #image.set_shape((FLAGS.TimeFrame, im_height, im_width, num_channels))
    #image = tf.cast(image, tf.float32)
    #image /= 255.0

    #image = tf.transpose(image, perm=[0, 3, 2, 1]) # transpose to mujoco setting for images
    #image = tf.reshape(image, [FLAGS.TimeFrame, -1])
    #num_preprocess_threads = 1 # TODO - enable this to be set to >1
    #min_queue_examples = 64 #128 #256
    #print 'Batching images'
    #images = tf.train.batch(
    #        [image],
    #        batch_size = batch_image_size,
    #        num_threads=num_preprocess_threads,
    #        capacity=min_queue_examples + 3 * batch_image_size,
    #        )
    #all_images = []
    #for i in xrange(FLAGS.end_test_set_size):
    #    image = images[i*(FLAGS.number_of_shot_test):(i+1)*(FLAGS.number_of_shot_test)]
    #    image = tf.reshape(image, [(FLAGS.number_of_shot_test)*FLAGS.TimeFrame, -1])
    #    all_images.append(image)
    selected_demo = dict(selected_demoX=X, selected_demoU=U, selected_demoO=Os, path=path)
    data_generator.selected_demo = selected_demo


def main():
    tf.set_random_seed(FLAGS.random_seed)
    np.random.seed(FLAGS.random_seed)
    random.seed(FLAGS.random_seed)

    graph = tf.Graph()
    gpu_options = tf.GPUOptions(per_process_gpu_memory_fraction=FLAGS.gpu_memory_fraction)
    tf_config = tf.ConfigProto(gpu_options=gpu_options)
    sess = tf.Session(graph=graph, config=tf_config)
    network_config = {
        'num_filters': [FLAGS.num_filters]*FLAGS.num_conv_layers,
        'strides': [[1, 2, 2, 1]]*FLAGS.num_strides + [[1, 1, 1, 1]]*(FLAGS.num_conv_layers-FLAGS.num_strides),
        'filter_size': FLAGS.filter_size,
        'image_width': FLAGS.im_width,
        'image_height': FLAGS.im_height,
        'image_channels': FLAGS.num_channels,
        'n_layers': FLAGS.num_fc_layers,
        'layer_size': FLAGS.layer_size,
        'initialization': FLAGS.init,
    }

    data_generator = DataGenerator()
    state_idx = data_generator.state_idx
    img_idx = range(len(state_idx), len(state_idx)+FLAGS.im_height*FLAGS.im_width*FLAGS.num_channels)
    model = MIL(data_generator._dU, state_idx=state_idx, img_idx=img_idx, network_config=network_config)

    exp_string = str(uuid.uuid4())
    log_dir = FLAGS.local_model_path + '/' + exp_string

    if FLAGS.train:
        with graph.as_default():
            train_image_tensors = data_generator.make_batch_tensor(network_config)
            inputa = train_image_tensors[:, :FLAGS.number_of_shot*FLAGS.TimeFrame, :]
            inputb = train_image_tensors[:, FLAGS.number_of_shot*FLAGS.TimeFrame:, :]
            train_input_tensors = {'inputa': inputa, 'inputb': inputb}
            val_image_tensors = data_generator.make_batch_tensor(network_config, train=False)
            inputa = val_image_tensors[:, :FLAGS.number_of_shot*FLAGS.TimeFrame, :]
            inputb = val_image_tensors[:, FLAGS.number_of_shot*FLAGS.TimeFrame:, :]
            val_input_tensors = {'inputa': inputa, 'inputb': inputb}
        model.init_network(graph, input_tensors=train_input_tensors)
        model.init_network(graph, input_tensors=val_input_tensors, prefix='Validation_')
    else:
        model.init_network(graph, prefix='Testing')
    with graph.as_default():
        # Set up saver.
        saver = tf.train.Saver(max_to_keep=10)
        # Initialize variables.
        init_op = tf.global_variables_initializer()
        sess.run(init_op, feed_dict=None)
        # Start queue runners (used for loading videos on the fly)
        tf.train.start_queue_runners(sess=sess)
    if FLAGS.train:
        train(graph, model, saver, sess, data_generator, log_dir)
    else:
        generate_test_demos(data_generator, network_config)
        evaluate_model(env, graph, model, data_generator, sess, exp_string, FLAGS.record_gifs, log_dir)

def load_scale_and_bias(data_path):
    with open(data_path, 'rb') as f:
        data = pickle.load(f)
        scale = data['scale']
        bias = data['bias']
    return scale, bias

def evaluate_model(env, graph, model, data_generator, sess, exp_string, record_gifs, log_dir):
    REACH_SUCCESS_THRESH = 0.05
    REACH_SUCCESS_TIME_RANGE = 10

    T = model.TimeFrame
    scale, bias = load_scale_and_bias('data/scale_and_bias_%s.pkl' % FLAGS.experiment)
    successes = []
    selected_demo = data_generator.selected_demo
    if record_gifs:
        record_gifs_dir = os.path.join(log_dir, 'evaluated_gifs')
        mkdir_p(record_gifs_dir)
    for i in xrange(len(selected_demo['selected_demoX'])):
        selected_demoO = selected_demo['selected_demoO'][i]
        selected_demoX = selected_demo['selected_demoX'][i]
        selected_demoU = selected_demo['selected_demoU'][i]
        path = selected_demo['path'][i]
        if record_gifs:
            gifs_dir = os.path.join(record_gifs_dir, path)
            mkdir_p(gifs_dir)
        dists = []
        # ob = env.reset()
        # use env.set_state here to arrange blocks
        Os = []
        for t in range(T):
            # import pdb; pdb.set_trace()
            env.render()
            time.sleep(0.05)
            obs, state = env.env.get_current_image_obs()
            Os.append(obs)
            obs = np.transpose(obs, [2, 1, 0]) / 255.0
            obs = obs.reshape(1, 1, -1)
            state = state.reshape(1, 1, -1)
            feed_dict = {
                model.obsa: selected_demoO,
                model.statea: selected_demoX.dot(scale) + bias,
                model.actiona: selected_demoU,
                model.obsb: obs,
                model.stateb: state.dot(scale) + bias
             }
            with graph.as_default():
                action = sess.run(model.test_act_op, feed_dict=feed_dict)
            ob, reward, done, reward_dict = env.step(np.squeeze(action))
            dist = -reward_dict['reward_dist']
            if t >= T - REACH_SUCCESS_TIME_RANGE:
                dists.append(dist)
        if np.amin(dists) <= REACH_SUCCESS_THRESH:
            successes.append(1.)
        else:
            successes.append(0.)
        if record_gifs:
            video = np.array(Os)
            record_gif_path = os.path.join(gifs_dir, 'output.gif')
            print 'Saving gif sample to :%s' % record_gif_path
            imageio.mimwrite(record_gif_path, video)
        env.render(close=True)
        if i % 5  == 0:
            print "Task %d: current success rate is %.5f" % (i, np.mean(successes))
    success_rate_msg = "Final success rate is %.5f" % (np.mean(successes))
    print success_rate_msg
    with open('logs/log_sim_vision_reach.txt', 'a') as f:
        f.write(exp_string + ':\n')
        f.write(success_rate_msg + '\n')



if __name__ == "__main__":
    main()
