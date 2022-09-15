from pkgutil import get_data
# from pretraining import load_json_config
import numpy as np
from paddle_models.MolEncoder import vdWGraph
import paddle.nn as nn
import paddle
from paddle_lulu.pahelix_utils import RandomSplitter, ScaffoldSplitter
from Geo_lulu import DownstreamTransformFn
from Predcollatefn import DownstreamCollateFn
from paddle_models.Downstream import DownstreamModel
from scipy.stats import pearsonr
from paddle_lulu.Inmemory import InMemoryDataset
from sklearn.metrics import mean_squared_error

import json
def load_json_config(path):
    """tbd"""
    return json.load(open(path, 'r'))

def test_save(args):
    compound_encoder_config = './config/geognn.json'
    compound_encoder_config = load_json_config(compound_encoder_config)

    dataset_name = args.dataset_name

    task_type = 'regr'
    metric = get_metric(dataset_name)

    model_config = './config/mlp.json'
    model_config = load_json_config(model_config)
    model_config['task_type'] = task_type

    label_mean, label_std = get_dataset_stat(dataset_name)

    compound_encoder = vdWGraph(compound_encoder_config)
    # init_model = 'FreeSolvResult/' + str(args.seed) + '/988_Free_encoder.pdparams'
    init_model = './save_encoder/epoch_' + args.init_model + '.pdparams'
    compound_encoder.set_state_dict(paddle.load(init_model))
    model = DownstreamModel(model_config, compound_encoder)

    # model.set_state_dict(paddle.load('FreeSolvResult/' + str(args.seed) + '/988_Free_model.pdparams'))

    transform_fn = DownstreamTransformFn()
    dataset = get_dataset(dataset_name, args)
    dataset.transform(transform_fn, 1)

    collate_fn = DownstreamCollateFn(
            atom_names=compound_encoder_config['atom_names'], 
            bond_names=compound_encoder_config['bond_names'],
            bond_float_names=compound_encoder_config['bond_float_names'],
            bond_angle_float_names=compound_encoder_config['bond_angle_float_names'],
            atom_van_bond_names=compound_encoder_config['atom_van_bond_names'],
            task_type=task_type)

    # valid_dataset = test_dataset
    splitter = create_splitter()
    train_dataset, valid_dataset, test_dataset = splitter.split(
            dataset, frac_train=0.8, frac_valid=0.1, frac_test=0.1)

    args.data_type = 'test'
    test_metric, test_pearson_epoch = evaluate(
                args, model, label_mean, label_std, 
                test_dataset, collate_fn, metric)
    args.data_type = 'valid'
    test_metric, test_pearson_epoch = evaluate(
            args, model, label_mean, label_std, 
            valid_dataset, collate_fn, metric)
    args.data_type = 'train'
    test_metric, test_pearson_epoch = evaluate(
            args, model, label_mean, label_std, 
            train_dataset, collate_fn, metric)    

    print(test_pearson_epoch)

def get_metric(dataset_name):
    """tbd"""
    # if dataset_name in ['esol', 'freesolv', 'lipophilicity']:
    return 'rmse'

def calc_rmse(labels, preds):
    """tbd"""
    # return np.sqrt(np.mean((preds - labels) ** 2))
    return np.sqrt(mean_squared_error(labels, preds))

def train(
        args, 
        model, label_mean, label_std,
        train_dataset, collate_fn, 
        criterion, encoder_opt, head_opt, task):
    """
    Define the train function 
    Args:
        args,model,train_dataset,collate_fn,criterion,encoder_opt,head_opt;
    Returns:
        the average of the list loss
    """
    data_gen = train_dataset.get_data_loader(
            batch_size=args.batch_size, 
            num_workers=args.num_workers, 
            shuffle=True,
            collate_fn=collate_fn)

    model.train()
    loss_return = paddle.to_tensor(0.)
    items = 0
    for atom_bond_graphs, bond_angle_graphs, labels in data_gen:
        if len(labels) < args.batch_size * 0.5:
            continue
        atom_bond_graphs = atom_bond_graphs.tensor()
        bond_angle_graphs = bond_angle_graphs.tensor()
        scaled_labels = (labels - label_mean) / (label_std + 1e-9)
        scaled_labels = labels
        scaled_labels = paddle.to_tensor(scaled_labels, 'float32')
        preds = model(atom_bond_graphs, bond_angle_graphs, task)
        # print(preds.shape, scaled_labels.shape)
        loss = criterion(preds, scaled_labels)
        items += preds.shape[0]
        # loss.backward()
        # encoder_opt.step()
        # head_opt.step()
        # encoder_opt.clear_grad()
        # head_opt.clear_grad()
        # list_loss.append(loss.numpy())

        loss_return += loss
        # list_loss.append(loss)
        # nodes_repr.append(nodes_repr_batch.numpy())
    # np.save('./dataset/train_nodes_repr.npy', np.concatenate(nodes_repr, 0))
    # return np.mean(list_loss)
    # print(len(list_loss))

    return loss_return


def evaluate(
        args, 
        model, label_mean, label_std,
        test_dataset, collate_fn, metric):
    """
    Define the evaluate function
    In the dataset, a proportion of labels are blank. So we use a `valid` tensor 
    to help eliminate these blank labels in both training and evaluation phase.
    """
    data_gen = test_dataset.get_data_loader(
            batch_size=args.batch_size, 
            num_workers=args.num_workers, 
            shuffle=False,
            collate_fn=collate_fn)
    total_pred = []
    total_label = []
    graph_repr = []

    model.eval()
    for atom_bond_graphs, bond_angle_graphs, labels in data_gen:
        atom_bond_graphs = atom_bond_graphs.tensor()
        bond_angle_graphs = bond_angle_graphs.tensor()
        
        # scaled_labels = labels.numpy() * label_std + label_mean
        labels = paddle.to_tensor(labels, 'float32')
        scaled_preds = model(atom_bond_graphs, bond_angle_graphs, 'tox')
        preds = scaled_preds.numpy() * label_std + label_mean
        total_pred.append(scaled_preds)
        total_label.append(labels.numpy())
        # graph_repr.append(g_repr.numpy())
        # nodes_repr.append(nodes_repr_batch.numpy())
    total_pred = np.concatenate(total_pred, 0).reshape(-1)
    total_label = np.concatenate(total_label, 0).reshape(-1)
    # graph_repr = np.concatenate(graph_repr, 0)
    # np.save('./data/free_' + args.data_type + '_fp.npy', graph_repr)
    # np.save('./data/free_' + args.data_type + '_label.npy', total_label)
    # print(total_pred)
    # print(total_label)
    # if metric == 'rmse':
    # np.save('./dataset/test_nodes_repr.npy', np.concatenate(nodes_repr, 0))
    return calc_rmse(total_label, total_pred), pearsonr(total_label, total_pred)[0]

def exempt_parameters(src_list, ref_list):
    """Remove element from src_list that is in ref_list"""
    res = []
    for x in src_list:
        flag = True
        for y in ref_list:
            if x is y:
                flag = False
                break
        if flag:
            res.append(x)
    return res

def get_dataset(dataset_name, args):

    path = './dataset/'  + dataset_name + '/'
    poses = np.load(path + 'conformations_2d.npy')
    nodes_number = np.load(path + 'nodes_number.npy')

    import pickle
    f = open(path + 'mols.pkl', 'rb')
    mols = pickle.load(f)
    f.close()

    y = np.load(path + 'y.npy').reshape([-1,1])

    # if dataset_name != 'FDA':
        
    #     path = './dataset/'  + dataset_name + '/testset/'
    #     poses1 = np.load(path + 'conformations.npy')
    #     nodes_number1 = np.load(path + 'nodes_number.npy')
    #     y1 = np.load(path + 'y.npy').reshape([-1,1])
    #     f = open(path + 'mols.pkl', 'rb')
    #     mols1 = pickle.load(f)
    #     f.close()

    #     poses = np.concatenate([poses, poses1], 0)
    #     nodes_number = np.concatenate([nodes_number, nodes_number1], 0)
    #     y = np.concatenate([y, y1],0)
    #     mols.extend(mols1)

    labels = y
    
    data_list = []

    for i in range(len(nodes_number)):
        nodes = nodes_number[i]
        pose = poses[i, :nodes, :].tolist()
        label = labels[i]
        mol = mols[i]
        data_list.append((mol, pose, label, args.ratio))
    
    data_list = InMemoryDataset(data_list=data_list)

    return data_list

def create_splitter(random=False):
    """Return a splitter according to the ``split_type``"""
    if random:
        splitter = RandomSplitter()
    else:
        splitter = ScaffoldSplitter()
    return splitter

def get_dataset_stat(dataset_name):
    label = np.load('./dataset/'  + dataset_name + '/y.npy')
    return np.mean(label), np.std(label)


def clear_main(args):
    encoder_lr = 0.001
    head_lr = 0.001
    compound_encoder_config = './config/geognn.json'
    compound_encoder_config = load_json_config(compound_encoder_config)

    dataset_name = args.dataset_name

    task_type = 'regr'
    metric = get_metric(dataset_name)

    model_config = './config/mlp.json'
    model_config = load_json_config(model_config)
    model_config['task_type'] = task_type

    compound_encoder = vdWGraph(compound_encoder_config)
    print('loading init_model..:', args.init_model)

    init_model = './save_encoder/epoch_' + args.init_model + '.pdparams'
    compound_encoder.set_state_dict(paddle.load(init_model))

    model = DownstreamModel(model_config, compound_encoder)

    criterion = nn.MSELoss()

    encoder_params = compound_encoder.parameters()
    head_params = exempt_parameters(model.parameters(), encoder_params)

    encoder_opt = paddle.optimizer.Adam(encoder_lr, parameters=encoder_params)
    head_opt = paddle.optimizer.Adam(head_lr, parameters=head_params)
    print('Total param num: %s' % (len(model.parameters())))
    print('Encoder param num: %s' % (len(encoder_params)))
    print('Head param num: %s' % (len(head_params)))


    print('Processing data...')
    dataset = get_dataset(dataset_name, args)

    transform_fn = DownstreamTransformFn()
    dataset.transform(transform_fn, num_workers=args.num_workers)

    label_mean, label_std = get_dataset_stat(dataset_name)

    # valid_dataset = test_dataset
    if args.random:
        splitter = create_splitter(random = True)
        train_dataset, valid_dataset, test_dataset = splitter.split(
                dataset, frac_train=0.8, frac_valid=0.1, frac_test=0.1, seed=args.seed)
    else:
        splitter = create_splitter(random = False)
        train_dataset, valid_dataset, test_dataset = splitter.split(
                dataset, frac_train=0.8, frac_valid=0.1, frac_test=0.1)        

    print("Train/Valid/Test num: %s/%s/%s" % (
            len(train_dataset), len(valid_dataset), len(test_dataset)))

    ### start train
    list_val_metric = []
    collate_fn = DownstreamCollateFn(
            atom_names=compound_encoder_config['atom_names'], 
            bond_names=compound_encoder_config['bond_names'],
            bond_float_names=compound_encoder_config['bond_float_names'],
            bond_angle_float_names=compound_encoder_config['bond_angle_float_names'],
            atom_van_bond_names=compound_encoder_config['atom_van_bond_names'],
            task_type=task_type)
    
    import time
    start_time = time.time()
    val_rmse = 10.
    patient = 0
    for epoch_id in range(args.max_epoch):

        train_loss = train(
                args, model, label_mean, label_std, 
                train_dataset, collate_fn, 
                criterion, encoder_opt, head_opt, 'tox')
        
        train_loss.backward()

        encoder_opt.step()
        head_opt.step()
        encoder_opt.clear_grad()
        head_opt.clear_grad()

        val_metric, val_pearson_epoch = evaluate(
                args, model, label_mean, label_std, 
                valid_dataset, collate_fn, metric)
        
        test_metric, test_pearson_epoch = evaluate(
                args, model, label_mean, label_std, 
                test_dataset, collate_fn, metric)

        list_val_metric.append(val_metric)
        end_time = time.time()
        print()
        print("epoch:%s train/loss:%s" % (epoch_id, train_loss.numpy()) ,'time:',round((end_time - start_time), 2))
        print("         val/%s:%s pearson:%s" % ( metric, val_metric, val_pearson_epoch))

        if val_metric < val_rmse:
            patient = 0
            # val_pearson = val_pearson_epoch
            val_rmse = val_metric
            test_pearson = test_pearson_epoch
            test_rmse = test_metric
            print("         test/%s:%s pearson:%s" % ( metric, test_rmse, test_pearson))
        else:
            patient += 1
            if patient == 50:break

        start_time = end_time
    

    if args.random:
        f = open('free_record.txt', 'a')
        # f.write('\n')
        f.write('random: ' + args.dataset_name + ' init_model:' + str(args.init_model)+' seed:' + str(args.seed) +' rmse:' + str(round(test_rmse, 2)) + ' personr:' + str(round(test_pearson,3)) + '\n')
        f.close()
        print(args.ratio, test_rmse)

        # return test_rmse
    else:
        f = open('free_record.txt', 'a')
        f.write('scaffold: ' + args.dataset_name + ' init_model:' + str(args.init_model)+' seed:' + str(args.seed) +' rmse:' + str(round(test_rmse, 2)) + ' personr:' + str(round(test_pearson,3)) + '\n')
        f.close()        

def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--task", choices=['train', 'data'], default='train')

    parser.add_argument("--batch_size", type=int, default=512)
    parser.add_argument("--num_workers", type=int, default=1)
    parser.add_argument("--max_epoch", type=int, default=500)
    parser.add_argument("--dataset_name", default='FreeSolv')
    parser.add_argument("--init_model", default='40')
    parser.add_argument("--seed", type=int, default=185779)
    parser.add_argument("--ratio", type=float, default=0.07)
    parser.add_argument("--random", type=bool, default=False)

    import random
    args = parser.parse_args()


    if args.random:
        seed = random.randint(0, 1000)
        print(seed)
        args.seed = seed
        import os
        if not os.path.exists('./FreeSolvResult/' + str(args.seed)):
            os.mkdir('./FreeSolvResult/' + str(args.seed))
        clear_main(args)
    else:
        clear_main(args)


if __name__ == '__main__':
    main()