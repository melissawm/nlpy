import numpy as np

import logging
import logging.handlers

__docformat__ = 'restructuredtext'

class LinearOperator:
    """
    A linear operator is a linear mapping x -> A(x) such that the size of the
    input vector x is `nargin` and the size of the output is `nargout`. It can
    be visualized as a matrix of shape (`nargout`, `nargin`).
    """

    def __init__(self, nargin, nargout, **kwargs):
        self.nargin = nargin
        self.nargout = nargout
        self.shape = (nargout, nargin)

        # Log activity.
        self.log = kwargs.get('log', False)
        if self.log:
            self.logger = logging.getLogger('LINOP')
            self.logger.setLevel(logging.DEBUG)
            ch = logging.handlers.RotatingFileHandler('linop.log')
            ch.setLevel(logging.DEBUG)
            fmtr = logging.Formatter('%(asctime)s-%(name)s-%(levelname)s %(message)s')
            ch.setFormatter(fmtr)
            self.logger.addHandler(ch)
            self.logger.info('New linear operator with shape ' + str(self.shape))
        else:
            self.logger = None

        return


    def get_shape(self):
        return self.shape


    def __call__(self, *args, **kwargs):
        # An alias for __mul__.
        return self.__mul__(*args, **kwargs)


    def __mul__(self, x):
        raise NotImplementedError, 'Please subclass to implement __mul__.'



class SimpleLinearOperator(LinearOperator):
    """
    A linear operator constructed from a matvec and (possibly) a matvec_transp
    function.
    """

    def __init__(self, nargin, nargout, matvec,
                 matvec_transp=None, symmetric=False, **kwargs):
        LinearOperator.__init__(self, nargin, nargout, **kwargs)
        self.symmetric = symmetric
        self.transposed = kwargs.get('transposed', False)
        transpose_of = kwargs.get('transpose_of', None)

        self.__mul__ = matvec

        if symmetric:
            self.T = self
        else:
            if transpose_of is None:
                if matvec_transp is not None:
                    # Create 'pointer' to transpose operator.
                    self.T = SimpleLinearOperator(nargout, nargin,
                                                  matvec_transp,
                                                  matvec_transp=matvec,
                                                  transposed=not self.transposed,
                                                  transpose_of=self,
                                                  log=self.log)
                else:
                    self.T = None
            else:
                # Use operator supplied as transpose operator.
                if isinstance(transpose_of, LinearOperator):
                    self.T = transpose_of
                else:
                    msg = 'kwarg transposed_of must be a LinearOperator.'
                    msg += ' Got ' + str(transpose_of.__class__)
                    raise ValueError, msg



class PysparseLinearOperator(LinearOperator):
    """
    A linear operator constructed from any object implementing either `__mul__`
    or `matvec` and either `__rmul__` or `matvec_transp`, such as a `ll_mat`
    object or a `PysparseMatrix` object.
    """

    def __init__(self, A, symmetric=False, **kwargs):
        m, n = A.shape
        self.A = A
        self.symmetric = symmetric
        self.transposed = kwargs.get('transposed', False)
        transpose_of = kwargs.get('transpose_of', None)

        if self.transposed:

            LinearOperator.__init__(self, m, n, **kwargs)
            #self.shape = (self.nargin, self.nargout)
            if hasattr(A, '__rmul__'):
                self.__mul__ = A.__rmul__
            else:
                self.__mul__ = self._rmul

        else:

            LinearOperator.__init__(self, n, m, **kwargs)
            if hasattr(A, '__mul__'):
                self.__mul__ = A.__mul__
            else:
                self.__mul__ = self._mul

        if self.log:
            self.logger.info('New linop has transposed = ' + str(self.transposed))

        if symmetric:
            self.T = self
        else:
            if transpose_of is None:
                # Create 'pointer' to transpose operator.
                self.T = PysparseLinearOperator(self.A,
                                                transposed=not self.transposed,
                                                transpose_of=self,
                                                log=self.log)
            else:
                # Use operator supplied as transpose operator.
                if isinstance(transpose_of, LinearOperator):
                    self.T = transpose_of
                else:
                    msg = 'kwarg transposed_of must be a LinearOperator.'
                    msg += ' Got ' + str(transpose_of.__class__)
                    raise ValueError, msg

        return


    def _mul(self, x):
        # Make provision for the case where A does not implement __mul__.
        if x.shape != (self.nargin,):
            msg = 'Input has shape ' + str(x.shape)
            msg += ' instead of (%d,)' % self.nargin
            raise ValueError, msg
        Ax = np.empty(self.nargout)
        self.A.matvec(x, Ax)
        return Ax


    def _rmul(self, y):
        # Make provision for the case where A does not implement __rmul__.
        # This method is only relevant when transposed=True.
        if y.shape != (self.nargin,):  # This is the transposed op's nargout!
            msg = 'Input has shape ' + str(y.shape)
            msg += ' instead of (%d,)' % self.nargin
            raise ValueError, msg
        ATy = np.empty(self.nargout)   # This is the transposed op's nargin!
        self.A.matvec_transp(y, ATy)
        return ATy



class SquaredLinearOperator(LinearOperator):
    """
    Given a linear operator `A`, build the linear operator `A.T * A`. If
    `transpose` is set to `True`, build `A * A.T` instead. This may be useful
    for solving one of the normal equations

    |           A'Ax = A'b
    |           AA'y = Ag

    which are the optimality conditions of the linear least-squares problems

    |          minimize{in x}  |Ax-b|
    |          minimize{in y}  |A'y-g|

    in the Euclidian norm.
    """

    def __init__(self, A, **kwargs):
        m, n = A.shape
        LinearOperator.__init__(self, n, m, **kwargs)
        self.transposed = kwargs.get('transposed', False)
        if isinstance(A, LinearOperator):
            self.A = A
        else:
            self.A = PysparseLinearOperator(A, transposed=False)
        self.symmetric = True
        if self.transposed:
            self.shape = (m, m)
            self.__mul__ = self._rmul
        else:
            self.shape = (n, n)
            self.__mul__ = self._mul
        if self.log:
            self.logger.info('New squared operator with shape ' + str(self.shape))
        self.T = self


    def _mul(self, x):
        return self.A.T * (self.A * x)


    def _rmul(self, x):
        return self.A * (self.A.T * x)



if __name__ == '__main__':
    from pysparse.sparse.pysparseMatrix import PysparseMatrix as sp
    from nlpy.model import AmplModel
    from nlpy.optimize.solvers.lsqr import LSQRFramework
    import numpy as np
    import sys

    np.set_printoptions(precision=3, linewidth=80, threshold=10, edgeitems=3)

    nlp = AmplModel(sys.argv[1])
    J = sp(matrix=nlp.jac(nlp.x0))
    #J = nlp.jac(nlp.x0)
    e1 = np.ones(J.shape[0])
    e2 = np.ones(J.shape[1])

    #print 'Explicitly:'
    #print 'J*e2 = ', J*e2
    #print "J'*e1 = ", e1*J

    print 'Testing PysparseLinearOperator:'
    op = PysparseLinearOperator(J)
    print 'op.shape = ', op.shape
    print 'op.T.shape = ', op.T.shape
    print 'op * e2 = ', op * e2
    print "op.T * e1 = ", op.T * e1
    print 'op.T.T * e2 = ', op.T.T * e2
    print 'op.T.T.T * e1 = ', op.T.T.T * e1
    print 'With call:'
    print 'op(e2) = ', op(e2)
    print 'op.T(e1) = ', op.T(e1)
    print 'op.T.T is op : ', (op.T.T is op)
    print
    print 'Testing SimpleLinearOperator:'
    op = SimpleLinearOperator(J.shape[1], J.shape[0],
                              lambda v: J*v,
                              matvec_transp=lambda u: u*J)
    print 'op.shape = ', op.shape
    print 'op.T.shape = ', op.T.shape
    print 'op * e2 = ', op * e2
    print 'e1.shape = ', e1.shape
    print 'op.T * e1 = ', op.T * e1
    print 'op.T.T * e2 = ', op.T.T * e2
    print 'op(e2) = ', op(e2)
    print 'op.T(e1) = ', op.T(e1)
    print 'op.T.T is op : ', (op.T.T is op)
    print
    print 'Solving a constrained least-squares problem with LSQR:'
    lsqr = LSQRFramework(op)
    lsqr.solve(np.random.random(nlp.m), show=True)
    print
    print 'Building a SquaredLinearOperator:'
    op2 = SquaredLinearOperator(J, log=True)
    print 'op2 * e2 = ', op2 * e2
    print 'op.T * (op * e2) = ', op.T * (op * e2)
    op3 = SquaredLinearOperator(J, transpose=True, log=True)
    print 'op3 * e1 = ', op3 * e1
    print 'op * (op.T * e1) = ', op * (op.T * e1)