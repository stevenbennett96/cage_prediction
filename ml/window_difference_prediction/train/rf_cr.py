from sklearn.metrics import (mean_squared_error,
                             mean_absolute_error,
                             r2_score)
from sklearn.ensemble import RandomForestRegressor
from sklearn.utils import shuffle
from sklearn.preprocessing import LabelBinarizer
import numpy as np
import pymongo
import itertools as it


def window_difference(windows):
    if windows is None or len(windows) < 4:
        return None

    clusters = [list(windows)]

    # After this sum the differences in each group and then
    # sum the group totals.
    diff_sums = []
    for cluster in clusters:
        diff_sum = sum(abs(w1 - w2) for w1, w2 in
                       it.combinations(cluster, 2))

        diff_num = sum(1 for _ in it.combinations(cluster, 2))

        diff_sums.append(diff_sum / diff_num)

    return np.mean(diff_sums)


def get_fp(match, radius, bits, fp_tags):
    struct = next(s for s in match['structures'] if
                  s['calc_params'] == {'software': 'stk'})

    return next(fp['fp'] for fp in struct['fingerprints'] if
                fp['radius'] == radius and fp['bits'] == bits and
                all(tag in fp['type'] for tag in fp_tags))


def get_target(match):

    calc_params = {
                        'software': 'schrodinger2017-4',
                        'max_iter': 5000,
                        'md': {
                               'confs': 50,
                               'temp': 700,
                               'sim_time': 2000,
                               'time_step': 1.0,
                               'force_field': 16,
                               'max_iter': 2500,
                               'eq_time': 100,
                               'gradient': 0.05,
                               'timeout': None
                        },
                        'force_field': 16,
                        'restricted': 'both',
                        'timeout': None,
                        'gradient': 0.05
    }
    windows = next(struct['windows'] for
                   struct in match['structures'] if
                   struct['calc_params'] == calc_params)
    return window_difference(windows)


def load_data(db, radius, bits, fp_tags, labeller, query):
    fingerprints, topologies, targets = [], [], []
    for match in db.find(query):
        target = get_target(match)
        if target is None:
            continue
        targets.append(target)
        topologies.append(match['topology']['class'])
        fingerprints.append(get_fp(match, radius, bits, fp_tags))

    topologies = LabelBinarizer().fit_transform(topologies)
    fingerprints = np.concatenate((fingerprints, topologies), axis=1)
    fingerprints, targets = shuffle(fingerprints, targets)
    return np.array(fingerprints), np.array(targets)


def train(db, radius, bits, fp_tags, labeller, fg_name, reverse):
    """

    """
    print(fg_name, f'reverse {reverse}')
    q1 = {'tags': fg_name, 'topology.class': 'FourPlusSix'}
    q2 = {'tags': {'$nin': [fg_name], '$exists': True},
          'topology.class': 'FourPlusSix'}
    if reverse:
        q2, q1 = q1, q2

    fp_train, labels_train = load_data(
                                     db=db,
                                     radius=radius,
                                     bits=bits,
                                     fp_tags=fp_tags,
                                     labeller=labeller,
                                     query=q1)
    print('train dataset size:', len(labels_train))
    fp_test, labels_test = load_data(
                                     db=db,
                                     radius=radius,
                                     bits=bits,
                                     fp_tags=fp_tags,
                                     labeller=labeller,
                                     query=q2)
    print('test dataset size:', len(labels_test))

    reg = RandomForestRegressor(
                                n_estimators=100,
                                n_jobs=-1,
                                criterion='mse')
    reg.fit(fp_train, labels_train)
    expected = labels_test
    predicted = reg.predict(fp_test)

    print('mse', mean_squared_error(expected, predicted))
    print('mae', mean_absolute_error(expected, predicted))
    print('nmae', np.mean(np.absolute(expected-predicted)))
    print('r2', r2_score(expected, predicted))


def main():
    np.random.seed(2)
    client = pymongo.MongoClient('mongodb://localhost:27017/')
    fg_names = ['amine2aldehyde3',
                'aldehyde2amine3',
                'alkene2alkene3',
                'alkyne22alkyne23',
                # 'thiol2thiol3',
                'amine2carboxylic_acid3',
                'carboxylic_acid2amine3']
    for fg_name in fg_names:
        train(
              db=client.small.cages,
              radius=8,
              bits=512,
              fp_tags=['bb_count'],
              labeller='pywindow_plus',
              fg_name=fg_name,
              reverse=False)
        train(
              db=client.small.cages,
              radius=8,
              bits=512,
              fp_tags=['bb_count'],
              labeller='pywindow_plus',
              fg_name=fg_name,
              reverse=True)


if __name__ == '__main__':
    main()
