#!/usr/bin/env python
# encoding: utf-8
#
# Copyright © 2019, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import pickle
import warnings

import pytest
from six.moves import mock


def dummy_function(x1, x2):
    # type: (float, float) -> (float, float)
    return x1+x2, x1-x2


def domath1(w, x):
    "Output: y, z"
    y = w * x
    z = w / x
    return y, z


@pytest.fixture
def train_data():
    """Returns the Iris data set as (X, y) """

    try:
        import pandas as pd
    except ImportError:
        pytest.skip('Package `pandas` not found.')

    try:
        from sklearn import datasets
    except ImportError:
        pytest.skip('Package `sklearn` not found.')

    raw = datasets.load_iris()
    iris = pd.DataFrame(raw.data, columns=raw.feature_names)
    iris = iris.join(pd.DataFrame(raw.target))
    iris.columns = ['SepalLength', 'SepalWidth', 'PetalLength', 'PetalWidth', 'Species']
    iris['Species'] = iris['Species'].astype('category')
    iris.Species.cat.categories = raw.target_names
    return iris.iloc[:, 0:4], iris['Species']


@pytest.fixture
def sklearn_model(train_data):
    """Returns a simple Scikit-Learn model """

    try:
        from sklearn.linear_model import LogisticRegression
    except ImportError:
        pytest.skip('Package `sklearn` not found.')

    X, y = train_data
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        model = LogisticRegression(multi_class='multinomial', solver='lbfgs')
        model.fit(X, y)
    return model


@pytest.fixture
def sklearn_pipeline(train_data):
    from sklearn.pipeline import Pipeline
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.impute import SimpleImputer
    from sklearn.compose import ColumnTransformer

    X, y = train_data

    numeric_transformer = Pipeline([
        ('imputer', SimpleImputer(strategy='median')),
        ('scaler', StandardScaler())
    ])

    preprocessor = ColumnTransformer([
        ('num', numeric_transformer, X.columns)
    ])

    pipe = Pipeline([
        ('preprocess', preprocessor),
        ('classifier', GradientBoostingClassifier())
    ])

    pipe.fit(X, y)

    return pipe


@pytest.fixture
def pickle_file(tmpdir_factory, sklearn_model):
    """Returns the path to a file containing a pickled Scikit-Learn model """
    import os

    sklearn_model
    filename = str(tmpdir_factory.mktemp('models').join('model.pkl'))
    with open(filename, 'wb') as f:
        pickle.dump(sklearn_model, f)
    yield str(filename)
    os.remove(filename)


@pytest.fixture
def python_file(tmpdir_factory):
    """Returns the path to a file containing source code for a Python function."""
    import os

    filename = str(tmpdir_factory.mktemp('models').join('model.py'))
    with open(filename, 'w') as f:
        f.writelines(['def predict(a, b, c, d):\n',
                      '    # types: (int, int, int, int) -> double\n'
                      '    pass\n'])

    yield str(filename)
    os.remove(filename)


@pytest.fixture
def pickle_stream(sklearn_model):
    """Returns a byte stream containing a pickled Scikit-Learn model """

    return pickle.dumps(sklearn_model)


def test_from_inline():
    from sasctl.utils.pymas import from_inline, PyMAS

    p = from_inline(dummy_function)
    assert isinstance(p, PyMAS)


def test_from_pickle(train_data, pickle_file):
    import re
    from sasctl.utils.pymas import PyMAS, from_pickle

    X, y = train_data

    with mock.patch('uuid.uuid4') as mocked:
        mocked.return_value.hex = 'DF74A4B18C9E41A2A34B0053E123AA67'
        p = from_pickle(pickle_file, func_name='predict',
                        input_types=X, array_input=True)


    target = """
package _DF74A4B18C9E41A2A34B0053E123AA6 / overwrite=yes;
    dcl package pymas py;
    dcl package logger logr('App.tk.MAS');
    dcl varchar(67108864) character set utf8 pycode;
    dcl int revision;

    method score(
        double SepalLength,
        double SepalWidth,
        double PetalLength,
        double PetalWidth,
        in_out char var1,
        in_out integer rc,
        in_out char msg
        );
    
        if null(py) then do;
            py = _new_ pymas();
            rc = py.useModule('mypymodule', 1);
            if rc then do;
                rc = py.appendSrcLine('try:');
                rc = py.appendSrcLine('    import pickle, base64');
                rc = py.appendSrcLine('    bytes = "X"');
                rc = py.appendSrcLine('    obj = pickle.loads(base64.b64decode(bytes))');
                rc = py.appendSrcLine('    _compile_error = None');
                rc = py.appendSrcLine('except Exception as e:');
                rc = py.appendSrcLine('    _compile_error = e');
                rc = py.appendSrcLine('');
                rc = py.appendSrcLine('def wrapper(SepalLength, SepalWidth, PetalLength, PetalWidth):');
                rc = py.appendSrcLine('    "Output: var1, msg"');
                rc = py.appendSrcLine('    result = None');
                rc = py.appendSrcLine('    try:');
                rc = py.appendSrcLine('        global _compile_error');
                rc = py.appendSrcLine('        if _compile_error is not None:');
                rc = py.appendSrcLine('            raise _compile_error');
                rc = py.appendSrcLine('        msg = ""');
                rc = py.appendSrcLine('        import numpy as np');
                rc = py.appendSrcLine('        result = obj.predict(np.array([SepalLength,SepalWidth,PetalLength,PetalWidth]).reshape((1, -1)))');
                rc = py.appendSrcLine('        if result.size == 1:');
                rc = py.appendSrcLine('            result = np.asscalar(result)');
                rc = py.appendSrcLine('    except Exception as e:');
                rc = py.appendSrcLine('        msg = str(e)');
                rc = py.appendSrcLine('        if result is None:');
                rc = py.appendSrcLine('            result = tuple(None for i in range(1))');
                rc = py.appendSrcLine('    if isinstance(result, tuple):');
                rc = py.appendSrcLine('        return tuple(x for x in list(result) + [msg])');
                rc = py.appendSrcLine('    else: ');
                rc = py.appendSrcLine('        return result, msg');
                pycode = py.getSource();
                revision = py.publish(pycode, 'mypymodule');
                if revision lt 1 then do;
                    logr.log('e', 'py.publish() failed.');
                    rc = -1;
                    return;
                end;
            end;
            rc = py.useMethod('wrapper');
            if rc then return;
        end;
        rc = py.setDouble('SepalLength', SepalLength);    if rc then return;
        rc = py.setDouble('SepalWidth', SepalWidth);    if rc then return;
        rc = py.setDouble('PetalLength', PetalLength);    if rc then return;
        rc = py.setDouble('PetalWidth', PetalWidth);    if rc then return;
        rc = py.execute();    if rc then return;
        var1 = py.getString('var1');
        msg = py.getString('msg');
    end;
    
endpackage;
"""

    assert isinstance(p, PyMAS)

    # Drop leading \n caused by multiline comment formatting
    result = p.score_code()

    # Ignore byte string during comparison.  Pickle seems to change with
    # time / Python versions
    result = re.sub('bytes = .*', 'bytes = "X"\');', result)
    assert result == target.lstrip('\n')


def test_from_pickle_stream(train_data, pickle_stream):
    from sasctl.utils.pymas import PyMAS, from_pickle

    X, y = train_data
    p = from_pickle(pickle_stream, func_name='predict', input_types=X)
    assert isinstance(p, PyMAS)


def test_from_python_file(python_file):
    from sasctl.utils.pymas import PyMAS, from_python_file

    p = from_python_file(python_file, func_name='predict')
    assert isinstance(p, PyMAS)


def test_with_sklearn_pipeline(train_data, sklearn_pipeline):
    from sasctl.utils.pymas import PyMAS, from_pickle

    X, y = train_data
    p = from_pickle(pickle.dumps(sklearn_pipeline),
                    func_name='predict',
                    input_types=X)

    assert isinstance(p, PyMAS)
    assert len(p.variables) > 4  # 4 input features in Iris data set

@pytest.mark.usefixtures('session')
def test_publish_and_execute(tmpdir):
    import pickle
    from sasctl.utils.pymas import from_pickle
    from sasctl.services import microanalytic_score as mas

    sklearn = pytest.importorskip('sklearn')
    from sklearn import datasets
    from sklearn.linear_model import LinearRegression
    pd = pytest.importorskip('pandas')
    data = sklearn.datasets.load_boston()
    X = pd.DataFrame(data.data, columns=data.feature_names)
    y = pd.DataFrame(data.target, columns=['Price'])

    lm = LinearRegression()
    lm.fit(X, y)
    pkl = pickle.dumps(lm)
    p = from_pickle(pkl, 'predict', X, array_input=True)

    mas.create_module('sasctl_test', source=p.score_code(), language='ds2')
    x1 = {k.lower(): v for k, v in X.iloc[0, :].items()}
    result = mas.execute_module_step('sasctl_test', 'score', **x1)

    assert result['rc'] == 0
    assert result['var1'] == 24
    assert result['msg'] is None

