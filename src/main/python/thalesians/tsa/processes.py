import datetime as dt

import numpy as np
import scipy.linalg as la

import thalesians.tsa.checks as checks
import thalesians.tsa.distrs as distrs
import thalesians.tsa.numpyutils as npu
import thalesians.tsa.numpychecks as npc

class Process(object):
    def __init__(self, **kwargs):
        try:
            super(Process, self).__init__(**kwargs)
        except TypeError:
            super(Process, self).__init__()

class ItoProcess(Process):
    def __init__(self, processdim=1, noisedim=None, drift=None, diffusion=None, **kwargs):
        self.__processdim = processdim
        self.__noisedim = processdim if noisedim is None else noisedim
        # Note: the brackets around the lambdas below are essential, otherwise the result of the parsing will not be what we need:
        self.__drift = (lambda t, x: npu.rowof(self.__processdim, 0.)) if drift is None else drift
        self.__diffusion = (lambda t, x: npu.matrixof(self.__processdim, self.__noisedim, 0.)) if diffusion is None else diffusion
        super(ItoProcess, self).__init__(processdim=self.__processdim, noisedim=self.__noisedim, drift=self.__drift, diffusion=self.__diffusion, **kwargs)
        
    @property
    def processdim(self):
        return self.__processdim
    
    @property
    def noisedim(self):
        return self.__noisedim
    
    @property
    def drift(self):
        return self.__drift
    
    @property
    def diffusion(self):
        return self.__diffusion
    
    def __str__(self):
        return 'ItoProcess(processdim=%d, noisedim=%d)' % (self.__processdim, self.__noisedim)
    
class SolvedItoProcess(ItoProcess):
    def __init__(self, processdim=1, noisedim=None, drift=None, diffusion=None, **kwargs):
        super(SolvedItoProcess, self).__init__(processdim=processdim, noisedim=noisedim, drift=drift, diffusion=diffusion, **kwargs)
        
    def propagate(self, time, variate, time0, value0, state0=None):
        raise NotImplementedError()
    
    def __str__(self):
        return 'SolvedItoProcess(processdim=%d, noisedim=%d)' % (self.processdim, self.noisedim)

class MarkovProcess(Process):
    def __init__(self, processdim, timeunit=dt.timedelta(days=1), **kwargs):
        self.__processdim = checks.checkint(processdim)
        self.__timeunit = timeunit
        
        self.__cachedtime = None
        self.__cachedtime0 = None
        self.__cacheddistr0 = None
        self.__cacheddistr = None
        super(MarkovProcess, self).__init__(processdim=processdim, **kwargs)
        
    def propagatedistr(self, time, time0, distr0):
        if time == time0: return distr0
        if self.__cachedtime is None or self.__cachedtime != time or self.__cachedtime0 != time0 or self.__cacheddistr0 != distr0:
            timedelta = time - time0
            if isinstance(timedelta, dt.timedelta):
                timedelta = timedelta.total_seconds() / self.__timeunit.total_seconds()
            self.__cacheddistr = self._propagatedistrimpl(timedelta, distr0)
            self.__cachedtime = time
            self.__cachedtime0 = time0
            self.__cacheddistr0 = distr0
        return self.__cacheddistr
    
    def _propagatedistrimpl(self, timedelta, distr0):
        raise NotImplementedError()
    
    def __str__(self):
        return 'MarkovProcess(processdim=%d)' % self.__processdim
    
class SolvedItoMarkovProcess(MarkovProcess, SolvedItoProcess):
    def __init__(self, processdim=1, noisedim=None, drift=None, diffusion=None, **kwargs):
        super(SolvedItoMarkovProcess, self).__init__(processdim=processdim, noisedim=noisedim, drift=drift, diffusion=diffusion, **kwargs)
    
    def propagate(self, time, variate, time0, value0, state0=None):
        if self.noisedim != self.processdim:
            raise NotImplementedError('Cannot utilise the propagatedistr of the Markov process in propagate if noisedim != processdim; provide a custom implementation')
        if time == time0: return npu.tondim2(value0, ndim1tocol=True, copy=True)
        value0 = npu.tondim2(value0, ndim1tocol=True, copy=False)
        variate = npu.tondim2(variate, ndim1tocol=True, copy=False)
        distr = self.propagatedistr(time, time0, distrs.NormalDistr.creatediracdelta(value0))
        return distr.mean + np.dot(np.linalg.cholesky(distr.cov), variate)

    def __str__(self):
        return 'SolvedItoMarkovProcess(processdim=%d, noisedim=%d)' % (self.processdim, self.noisedim)

# TODO To be implemented
class KalmanProcess(MarkovProcess):
    def __init__(self):
        pass
    
class WienerProcess(SolvedItoMarkovProcess):
    def __init__(self, mean=None, vol=None):
        if mean is None and vol is None:
            mean = 0.; vol = 1.
        
        self.__mean, self.__vol = None, None
        
        if mean is not None:
            self.__mean = npu.tondim2(mean, ndim1tocol=True, copy=True)
            processdim = npu.nrow(self.__mean)
        if vol is not None:
            self.__vol = npu.tondim2(vol, ndim1tocol=True, copy=True)
            processdim = npu.nrow(self.__vol)
        
        if self.__mean is None: self.__mean = npu.colof(processdim, 0.)
        if self.__vol is None: self.__vol = np.eye(processdim)
        
        npc.checkcol(self.__mean)
        npc.checknrow(self.__mean, processdim)
        npc.checknrow(self.__vol, processdim)
        
        noisedim = npu.ncol(self.__vol)
        self.__cov = np.dot(self.__vol, self.__vol.T)
        
        npu.makeimmutable(self.__mean)
        npu.makeimmutable(self.__vol)
        npu.makeimmutable(self.__cov)
        
        super(WienerProcess, self).__init__(processdim=processdim, noisedim=noisedim, drift=lambda t, x: self.__mean, diffusion=lambda t, x: self.__vol)
        
    @staticmethod
    def create2d(mean1, mean2, sd1, sd2, cor):
        return WienerProcess(npu.col(mean1, mean2), distrs.NormalDistr.makevol2d(sd1, sd2, cor))
    
    @staticmethod
    def createfromcov(mean, cov):
        return WienerProcess(mean, distrs.NormalDistr.makevolfromcov(cov))
    
    @property
    def mean(self):
        return self.__mean
    
    @property
    def vol(self):
        return self.__vol
    
    @property
    def cov(self):
        return self.__cov
    
    def propagate(self, time, variate, time0, value0, state0=None):
        if time == time0: return npu.tondim2(value0, ndim1tocol=True, copy=True)
        value0 = npu.tondim2(value0, ndim1tocol=True, copy=False)
        variate = npu.tondim2(variate, ndim1tocol=True, copy=False)
        timedelta = time - time0
        return value0 + self.__mean * timedelta + np.dot(self.__vol, np.sqrt(timedelta) * variate)
    
    def _propagatedistrimpl(self, timedelta, distr0):
        mean = distr0.mean + self.__mean * timedelta
        cov = distr0.cov + timedelta * self.__cov
        return distrs.NormalDistr(mean=mean, cov=cov)
        
    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.__mean == other.__mean and self.__vol == other.__vol
        return False
    
    def __ne__(self, other):
        return not self.__eq__(other)

    def __str__(self):
        return 'WienerProcess(processdim=%d, noisedim=%d, mean=%s, vol=%s)' % (self.processdim, self.noisedim, str(self.__mean), str(self.__vol))

class OrnsteinUhlenbeckProcess(SolvedItoMarkovProcess):
    def __init__(self, transition=None, mean=None, vol=None):
        if transition is None and mean is None and vol is None:
            transition = 1.; mean = 0.; vol = 1.
            
        self.__transition, self.__mean, self.__vol = None, None, None
            
        if transition is not None:
            self.__transition = npu.tondim2(transition, ndim1tocol=True, copy=True)
            processdim = npu.nrow(self.__transition)
        if mean is not None:
            self.__mean = npu.tondim2(mean, ndim1tocol=True, copy=True)
            processdim = npu.nrow(self.__mean)
        if vol is not None:
            self.__vol = npu.tondim2(vol, ndim1tocol=True, copy=True)
            processdim = npu.nrow(self.__vol)
        
        if self.__transition is None: self.__transition = np.eye(processdim)
        if self.__mean is None: self.__mean = npu.colof(processdim, 0.)
        if self.__vol is None: self.__vol = np.eye(processdim)
        
        npc.checksquare(self.__transition)
        npc.checknrow(self.__transition, processdim)
        npc.checkcol(self.__mean)
        npc.checknrow(self.__mean, processdim)
        npc.checknrow(self.__vol, processdim)
        
        noisedim = npu.ncol(self.__vol)
        
        self.__transitionx2 = npu.kronsum(self.__transition, self.__transition)
        self.__transitionx2inverse = np.linalg.inv(self.__transitionx2)
        self.__cov = np.dot(self.__vol, self.__vol.T)
        self.__covvec = npu.vec(self.__cov)
        
        self.__cachedmeanreversionfactor = None
        self.__cachedmeanreversionfactortimedelta = None
        self.__cachedmeanreversionfactorsquared = None
        self.__cachedmeanreversionfactorsquaredtimedelta = None
        
        npu.makeimmutable(self.__transition)
        npu.makeimmutable(self.__transitionx2)
        npu.makeimmutable(self.__transitionx2inverse)
        npu.makeimmutable(self.__mean)
        npu.makeimmutable(self.__vol)
        npu.makeimmutable(self.__cov)
        npu.makeimmutable(self.__covvec)
        
        super(OrnsteinUhlenbeckProcess, self).__init__(processdim=processdim, noisedim=noisedim, drift=lambda t, x: -np.dot(self.__transition, x - self.__mean), diffusion=lambda t, x: self.__vol)
        
    @property
    def transition(self):
        return self.__transition
        
    @property
    def mean(self):
        return self.__mean
    
    @property
    def vol(self):
        return self.__vol
    
    def meanreversionfactor(self, timedelta):
        if self.__cachedmeanreversionfactortimedelta is None or self.__cachedmeanreversionfactortimedelta != timedelta:
            self.__cachedmeanreversionfactortimedelta = timedelta
            self.__cachedmeanreversionfactor = la.expm(self.__transition * (-timedelta))
        return self.__cachedmeanreversionfactor
    
    def meanreversionfactorsquared(self, timedelta):
        if self.__cachedmeanreversionfactorsquaredtimedelta is None or self.__cachedmeanreversionfactorsquaredtimedelta != timedelta:
            self.__cachedmeanreversionfactorsquaredtimedelta = timedelta
            self.__cachedmeanreversionfactorsquared = la.expm(self.__transitionx2 * (-timedelta))
        return self.__cachedmeanreversionfactorsquared
        
    def noisecovariance(self, timedelta):
        mrfsquared = self.meanreversionfactorsquared(timedelta)
        eyeminusmrfsquared = np.eye(self.processdim) - mrfsquared
        return npu.unvec(np.dot(np.dot(self.__transitionx2inverse, eyeminusmrfsquared), self.__covvec), self.processdim)
        
    def propagate(self, time, variate, time0, value0, state0=None):
        if time == time0: return npu.tondim2(value0, ndim1tocol=True, copy=True)
        value0 = npu.tondim2(value0, ndim1tocol=True, copy=False)
        variate = npu.tondim2(variate, ndim1tocol=True, copy=False)
        timedelta = time - time0
        mrf = self.meanreversionfactor(timedelta)
        eyeminusmrf = np.eye(self.processdim) - mrf
        m = np.dot(mrf, value0) + np.dot(eyeminusmrf, self.__mean)
        c = self.noisecovariance(timedelta)
        return m + np.dot(np.linalg.cholesky(c), variate)
        
    def _propagatedistrimpl(self, timedelta, distr0):
        value0 = distr0.mean
        mrf = self.meanreversionfactor(timedelta)
        eyeminusmrf = np.eye(self.processdim) - mrf
        m = np.dot(mrf, value0) + np.dot(eyeminusmrf, self.__mean)
        c = np.dot(np.dot(mrf, distr0.cov), mrf.T) + self.noisecovariance(timedelta)
        return distrs.NormalDistr(mean=m, cov=c)
    
    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.__mean == other.__mean and self.__vol == other.__vol
        return False
    
    def __ne__(self, other):
        return not self.__eq__(other)

    def __str__(self):
        return 'OrnsteinUhlenbeckProcess(processdim=%d, noisedim=%d, transition=%s, mean=%s, vol=%s)' % (self.processdim, self.noisedim, str(self.__transition), str(self.__mean), str(self.__vol))
    